"""
semantic.py — Stage 3 of the JOCKY compiler: Semantic Analysis.

Walks the AST to:
  1. Populate the symbol table (track declared names and their types).
  2. Verify that every name used was declared.
  3. Check that types are compatible across operations.
  4. Annotate every expression node with its inferred type.

Input:  Program AST (from parser)
Output: Same AST, with inferred_type fields filled in; raises SemanticError on violations.
"""

from .ast_nodes import (
    Program, FunctionDef, Param, Block,
    VarDecl, Assignment, IfStatement, LoopStatement,
    ReturnStatement, BreakStatement, SkipStatement, ExpressionStatement,
    BinaryExpression, UnaryExpression, FunctionCall,
    Identifier, NumberLiteral, FloatLiteral, StringLiteral,
    BoolLiteral, EmptyLiteral,
)
from .symbol_table import SymbolTable, SymbolError


class SemanticError(Exception):
    pass


# All JOCKY standard library functions with their parameter and return types.
# These are pre-populated into the symbol table before user code is analysed.
STDLIB_SIGNATURES: dict[str, tuple[list[str], str]] = {
    'report':        (['text'],              'nothing'),
    'procs_list':    ([],                    'raw'),
    'proc_count':    (['raw'],               'num'),
    'proc_name':     (['raw', 'num'],        'text'),
    'proc_pid':      (['raw', 'num'],        'num'),
    'proc_kill':     (['num'],               'nothing'),
    'proc_mem_read': (['num', 'num', 'num'], 'raw'),
    'net_conns':     ([],                    'raw'),
    'net_sniff':     (['num'],               'raw'),
    'reg_read':      (['text', 'text'],      'text'),
    'reg_list':      (['text'],              'raw'),
    'file_list':     (['text'],              'raw'),
    'file_read':     (['text'],              'raw'),
    'sys_info':      ([],                    'raw'),
    'hash_file':     (['text'],              'raw'),
}

# Types that are considered numeric (arithmetic is allowed on them)
NUMERIC = {'num', 'dec'}


class SemanticAnalyzer:
    def __init__(self):
        self.symtab = SymbolTable()
        self.current_return_type: str = 'nothing'
        self.errors: list[str] = []
        self._seed_stdlib()

    def _seed_stdlib(self) -> None:
        for name, (params, ret) in STDLIB_SIGNATURES.items():
            self.symtab.declare_function(name, params, ret)

    # ─── Error collection ────────────────────────────────────────────────────

    def _err(self, msg: str, line: int) -> None:
        self.errors.append(f"  Line {line}: {msg}")

    # ─── Entry point ─────────────────────────────────────────────────────────

    def analyze(self, program: Program) -> None:
        """Analyse the whole program.  Raises SemanticError if any errors found."""
        # Pass 1: register every user function signature so forward calls work
        for func in program.functions:
            param_types = [p.type_annotation for p in func.params]
            try:
                self.symtab.declare_function(
                    func.name, param_types, func.return_type, func.line
                )
            except SymbolError as e:
                self._err(str(e), func.line)

        # Pass 2: analyse function bodies
        for func in program.functions:
            self._visit_function(func)

        if self.errors:
            raise SemanticError("Semantic analysis failed:\n" + "\n".join(self.errors))

    # ─── Visitors ────────────────────────────────────────────────────────────

    def _visit_function(self, node: FunctionDef) -> None:
        self.current_return_type = node.return_type
        self.symtab.enter_scope()
        for param in node.params:
            try:
                self.symtab.declare_var(param.name, param.type_annotation,
                                        param.line, kind='parameter')
            except SymbolError as e:
                self._err(str(e), param.line)
        self._visit_block(node.body)
        self.symtab.exit_scope()

    def _visit_block(self, node: Block) -> None:
        self.symtab.enter_scope()
        for stmt in node.statements:
            self._visit_stmt(stmt)
        self.symtab.exit_scope()

    def _visit_stmt(self, node) -> None:
        if isinstance(node, VarDecl):
            self._visit_var_decl(node)
        elif isinstance(node, Assignment):
            self._visit_assignment(node)
        elif isinstance(node, IfStatement):
            self._visit_if(node)
        elif isinstance(node, LoopStatement):
            self._visit_loop(node)
        elif isinstance(node, ReturnStatement):
            self._visit_return(node)
        elif isinstance(node, ExpressionStatement):
            self._visit_expr(node.expression)
        elif isinstance(node, (BreakStatement, SkipStatement)):
            pass   # always valid (loop context not tracked for SIH scope)

    def _visit_var_decl(self, node: VarDecl) -> None:
        init_type = self._visit_expr(node.initializer)
        self._check_assignable(node.type_annotation, init_type,
                               f"variable '{node.name}'", node.line)
        try:
            self.symtab.declare_var(node.name, node.type_annotation, node.line)
        except SymbolError as e:
            self._err(str(e), node.line)

    def _visit_assignment(self, node: Assignment) -> None:
        try:
            sym = self.symtab.lookup_var(node.name, node.line)
        except SymbolError as e:
            self._err(str(e), node.line)
            return
        val_type = self._visit_expr(node.value)
        self._check_assignable(sym.type_str, val_type,
                               f"assignment to '{node.name}'", node.line)

    def _visit_if(self, node: IfStatement) -> None:
        cond_type = self._visit_expr(node.condition)
        if cond_type not in ('flag', 'unknown'):
            self._err(
                f"'check' condition must be 'flag', got '{cond_type}'",
                node.line,
            )
        self._visit_block(node.then_body)
        if node.else_body:
            self._visit_block(node.else_body)

    def _visit_loop(self, node: LoopStatement) -> None:
        cond_type = self._visit_expr(node.condition)
        if cond_type not in ('flag', 'unknown'):
            self._err(
                f"'loop' condition must be 'flag', got '{cond_type}'",
                node.line,
            )
        self._visit_block(node.body)

    def _visit_return(self, node: ReturnStatement) -> None:
        if node.value is None:
            if self.current_return_type != 'nothing':
                self._err(
                    f"Empty 'give' in a function declared to return '{self.current_return_type}'",
                    node.line,
                )
            return
        val_type = self._visit_expr(node.value)
        self._check_assignable(self.current_return_type, val_type,
                               "return value", node.line)

    # ─── Expression visitor — returns the inferred type string ───────────────

    def _visit_expr(self, node) -> str:
        if isinstance(node, NumberLiteral):
            node.inferred_type = 'num';  return 'num'
        if isinstance(node, FloatLiteral):
            node.inferred_type = 'dec';  return 'dec'
        if isinstance(node, StringLiteral):
            node.inferred_type = 'text'; return 'text'
        if isinstance(node, BoolLiteral):
            node.inferred_type = 'flag'; return 'flag'
        if isinstance(node, EmptyLiteral):
            node.inferred_type = 'nothing'; return 'nothing'

        if isinstance(node, Identifier):
            return self._visit_identifier(node)
        if isinstance(node, BinaryExpression):
            return self._visit_binary(node)
        if isinstance(node, UnaryExpression):
            return self._visit_unary(node)
        if isinstance(node, FunctionCall):
            return self._visit_call(node)

        return 'unknown'

    def _visit_identifier(self, node: Identifier) -> str:
        try:
            sym = self.symtab.lookup_var(node.name, node.line)
            node.inferred_type = sym.type_str
            return sym.type_str
        except SymbolError as e:
            self._err(str(e), node.line)
            node.inferred_type = 'unknown'
            return 'unknown'

    def _visit_binary(self, node: BinaryExpression) -> str:
        lt = self._visit_expr(node.left)
        rt = self._visit_expr(node.right)
        op = node.operator

        if op in ('+', '-', '*', '/', 'mod'):
            if lt in NUMERIC and rt in NUMERIC:
                result = 'dec' if 'dec' in (lt, rt) else 'num'
            elif lt == 'unknown' or rt == 'unknown':
                result = 'unknown'
            else:
                self._err(
                    f"Operator '{op}' requires numeric types, got '{lt}' and '{rt}'",
                    node.line,
                )
                result = 'unknown'
            node.inferred_type = result
            return result

        if op in ('is', 'isnt'):
            if lt != rt and 'unknown' not in (lt, rt):
                if not (lt in NUMERIC and rt in NUMERIC):
                    self._err(
                        f"Operator '{op}' requires matching types, got '{lt}' and '{rt}'",
                        node.line,
                    )
            node.inferred_type = 'flag'
            return 'flag'

        if op in ('gt', 'lt', 'gte', 'lte'):
            if lt not in NUMERIC and lt != 'unknown':
                self._err(
                    f"Operator '{op}' requires numeric left operand, got '{lt}'",
                    node.line,
                )
            if rt not in NUMERIC and rt != 'unknown':
                self._err(
                    f"Operator '{op}' requires numeric right operand, got '{rt}'",
                    node.line,
                )
            node.inferred_type = 'flag'
            return 'flag'

        if op in ('also', 'or'):
            if lt not in ('flag', 'unknown'):
                self._err(f"'{op}' requires 'flag' left operand, got '{lt}'", node.line)
            if rt not in ('flag', 'unknown'):
                self._err(f"'{op}' requires 'flag' right operand, got '{rt}'", node.line)
            node.inferred_type = 'flag'
            return 'flag'

        node.inferred_type = 'unknown'
        return 'unknown'

    def _visit_unary(self, node: UnaryExpression) -> str:
        ot = self._visit_expr(node.operand)
        if node.operator == 'flip':
            if ot not in ('flag', 'unknown'):
                self._err(f"'flip' requires 'flag' operand, got '{ot}'", node.line)
            node.inferred_type = 'flag'
            return 'flag'
        if node.operator == '-':
            if ot not in NUMERIC and ot != 'unknown':
                self._err(f"Unary '-' requires numeric operand, got '{ot}'", node.line)
            node.inferred_type = ot if ot != 'unknown' else 'num'
            return node.inferred_type
        node.inferred_type = 'unknown'
        return 'unknown'

    def _visit_call(self, node: FunctionCall) -> str:
        try:
            sym = self.symtab.lookup_function(node.name, node.line)
        except SymbolError as e:
            self._err(str(e), node.line)
            node.inferred_type = 'unknown'
            return 'unknown'

        expected = len(sym.param_types)
        got      = len(node.arguments)
        if expected != got:
            self._err(
                f"Function '{node.name}' expects {expected} argument(s), got {got}",
                node.line,
            )

        for arg in node.arguments:
            self._visit_expr(arg)

        node.inferred_type = sym.return_type
        return sym.return_type

    # ─── Type compatibility helper ────────────────────────────────────────────

    def _check_assignable(self, target: str, source: str,
                           context: str, line: int) -> None:
        if source == 'unknown' or target == 'unknown':
            return  # already reported elsewhere
        if target == source:
            return
        # num and dec are mutually assignable (auto-convert)
        if target in NUMERIC and source in NUMERIC:
            return
        # raw accepts nothing (null)
        if target == 'raw' and source == 'nothing':
            return
        self._err(
            f"Type mismatch in {context}: "
            f"expected '{target}', got '{source}'",
            line,
        )
