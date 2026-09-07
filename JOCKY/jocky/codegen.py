"""
codegen.py — Stage 4 of the JOCKY compiler: LLVM IR Generation.

Walks the annotated AST and emits LLVM IR instructions using the llvmlite
Python bindings.

The central idea:
  - Every expression node becomes a Value (the result of some IR instruction).
  - Variables are stored on the stack (alloca) and loaded/stored as needed.
  - Control flow (if/loop) is represented by multiple connected basic blocks.
  - Function calls emit a 'call' instruction referencing a declared function.

Input:  Program AST (semantic-annotated)
Output: llvmlite ir.Module  (the complete LLVM IR module)
"""

import llvmlite.ir as ir
from .ast_nodes import (
    Program, FunctionDef, Block,
    VarDecl, Assignment, IfStatement, LoopStatement,
    ReturnStatement, BreakStatement, SkipStatement, ExpressionStatement,
    BinaryExpression, UnaryExpression, FunctionCall,
    Identifier, NumberLiteral, FloatLiteral, StringLiteral,
    BoolLiteral, EmptyLiteral,
)


class CodegenError(Exception):
    pass


class CodeGenerator:
    """
    Generates an LLVM IR module from a JOCKY AST.
    """

    def __init__(self, source_name: str = 'jocky_module'):
        self.module   = ir.Module(name=source_name)
        self.builder  = None             # ir.IRBuilder, set per function
        self.cur_func = None             # current ir.Function

        # Maps variable name → alloca pointer for the current function
        self.value_table: dict[str, ir.AllocaInstr] = {}

        # Maps function name → ir.Function (for both user & stdlib)
        self.func_table: dict[str, ir.Function] = {}

        # Loop control stacks (pushed/popped on entering/leaving loops)
        self.break_stack: list[ir.Block]    = []  # target for 'stop'
        self.continue_stack: list[ir.Block] = []  # target for 'skip'

        # Counter for unique global string names
        self._str_idx = 0

        # ── Handy type references ────────────────────────────────────────────
        self.i1    = ir.IntType(1)
        self.i8    = ir.IntType(8)
        self.i32   = ir.IntType(32)
        self.i64   = ir.IntType(64)
        self.f64   = ir.DoubleType()
        self.voidT = ir.VoidType()
        self.i8p   = ir.IntType(8).as_pointer()

        self._declare_stdlib()

    # ─── Type helpers ────────────────────────────────────────────────────────

    def _jocky_to_llvm(self, type_str: str) -> ir.Type:
        return {
            'num':     self.i64,
            'dec':     self.f64,
            'text':    self.i8p,
            'flag':    self.i1,
            'raw':     self.i8p,
            'nothing': self.voidT,
        }.get(type_str, self.i64)

    # ─── Standard library declarations ───────────────────────────────────────

    def _declare_stdlib(self) -> None:
        """Emit external function declarations for every JOCKY stdlib function."""
        decls = {
            'report':        (self.voidT, [self.i8p]),
            'procs_list':    (self.i8p,   []),
            'proc_count':    (self.i64,   [self.i8p]),
            'proc_name':     (self.i8p,   [self.i8p, self.i64]),
            'proc_pid':      (self.i64,   [self.i8p, self.i64]),
            'proc_kill':     (self.voidT, [self.i64]),
            'proc_mem_read': (self.i8p,   [self.i64, self.i64, self.i64]),
            'net_conns':     (self.i8p,   []),
            'net_sniff':     (self.i8p,   [self.i64]),
            'reg_read':      (self.i8p,   [self.i8p, self.i8p]),
            'reg_list':      (self.i8p,   [self.i8p]),
            'file_list':     (self.i8p,   [self.i8p]),
            'file_read':     (self.i8p,   [self.i8p]),
            'sys_info':      (self.i8p,   []),
            'hash_file':     (self.i8p,   [self.i8p]),
        }
        for name, (ret, params) in decls.items():
            fn_type = ir.FunctionType(ret, params)
            fn      = ir.Function(self.module, fn_type, name=name)
            self.func_table[name] = fn

        # strcmp is needed for text comparison (is / isnt on text values)
        strcmp_type = ir.FunctionType(self.i32, [self.i8p, self.i8p])
        strcmp = ir.Function(self.module, strcmp_type, name='strcmp')
        self.func_table['strcmp'] = strcmp

    # ─── Entry point ─────────────────────────────────────────────────────────

    def generate(self, program: Program) -> ir.Module:
        # Pass 1: declare all user functions (so forward calls work)
        for func_def in program.functions:
            self._declare_user_func(func_def)
        # Pass 2: generate function bodies
        for func_def in program.functions:
            self._gen_function(func_def)
        return self.module

    # ─── Function handling ───────────────────────────────────────────────────

    def _declare_user_func(self, node: FunctionDef) -> None:
        param_types = [self._jocky_to_llvm(p.type_annotation) for p in node.params]
        ret_type    = self._jocky_to_llvm(node.return_type)
        fn_type     = ir.FunctionType(ret_type, param_types)
        fn          = ir.Function(self.module, fn_type, name=node.name)
        for i, param in enumerate(node.params):
            fn.args[i].name = param.name
        self.func_table[node.name] = fn

    def _gen_function(self, node: FunctionDef) -> None:
        fn           = self.func_table[node.name]
        self.cur_func = fn
        self.value_table = {}

        # Create entry block and builder
        entry = fn.append_basic_block('entry')
        self.builder = ir.IRBuilder(entry)

        # Allocate stack slots for each parameter and store the argument value
        for i, param in enumerate(node.params):
            llvm_type = self._jocky_to_llvm(param.type_annotation)
            alloca    = self.builder.alloca(llvm_type, name=param.name)
            self.builder.store(fn.args[i], alloca)
            self.value_table[param.name] = alloca

        # Generate the body
        self._gen_block(node.body)

        # Add an implicit return if the function falls off the end
        if not self.builder.block.is_terminated:
            if node.return_type == 'nothing':
                self.builder.ret_void()
            else:
                ret_type = self._jocky_to_llvm(node.return_type)
                self.builder.ret(ir.Constant(ret_type, 0))

    # ─── Statements ──────────────────────────────────────────────────────────

    def _gen_block(self, node: Block) -> None:
        for stmt in node.statements:
            if self.builder.block.is_terminated:
                break   # dead code after ret/br — skip
            self._gen_stmt(stmt)

    def _gen_stmt(self, node) -> None:
        if isinstance(node, VarDecl):
            self._gen_var_decl(node)
        elif isinstance(node, Assignment):
            self._gen_assignment(node)
        elif isinstance(node, IfStatement):
            self._gen_if(node)
        elif isinstance(node, LoopStatement):
            self._gen_loop(node)
        elif isinstance(node, ReturnStatement):
            self._gen_return(node)
        elif isinstance(node, BreakStatement):
            if self.break_stack:
                self.builder.branch(self.break_stack[-1])
        elif isinstance(node, SkipStatement):
            if self.continue_stack:
                self.builder.branch(self.continue_stack[-1])
        elif isinstance(node, ExpressionStatement):
            self._gen_expr(node.expression)

    def _gen_var_decl(self, node: VarDecl) -> None:
        llvm_type = self._jocky_to_llvm(node.type_annotation)
        alloca    = self.builder.alloca(llvm_type, name=node.name)
        init_val  = self._gen_expr(node.initializer)
        init_val  = self._coerce(init_val, llvm_type)
        self.builder.store(init_val, alloca)
        self.value_table[node.name] = alloca

    def _gen_assignment(self, node: Assignment) -> None:
        if node.name not in self.value_table:
            raise CodegenError(f"Undefined variable '{node.name}' (line {node.line})")
        alloca     = self.value_table[node.name]
        target_type = alloca.type.pointee
        new_val    = self._gen_expr(node.value)
        new_val    = self._coerce(new_val, target_type)
        self.builder.store(new_val, alloca)

    def _gen_if(self, node: IfStatement) -> None:
        cond_val = self._gen_expr(node.condition)
        cond_val = self._to_bool(cond_val)

        fn           = self.cur_func
        then_bb      = fn.append_basic_block('then')
        else_bb      = fn.append_basic_block('else')
        merge_bb     = fn.append_basic_block('merge')

        self.builder.cbranch(cond_val, then_bb, else_bb)

        # then branch
        self.builder.position_at_end(then_bb)
        self._gen_block(node.then_body)
        if not self.builder.block.is_terminated:
            self.builder.branch(merge_bb)

        # else branch
        self.builder.position_at_end(else_bb)
        if node.else_body:
            self._gen_block(node.else_body)
        if not self.builder.block.is_terminated:
            self.builder.branch(merge_bb)

        self.builder.position_at_end(merge_bb)

    def _gen_loop(self, node: LoopStatement) -> None:
        fn          = self.cur_func
        cond_bb     = fn.append_basic_block('loop_cond')
        body_bb     = fn.append_basic_block('loop_body')
        exit_bb     = fn.append_basic_block('loop_exit')

        self.break_stack.append(exit_bb)
        self.continue_stack.append(cond_bb)

        self.builder.branch(cond_bb)

        # Condition block
        self.builder.position_at_end(cond_bb)
        cond_val = self._gen_expr(node.condition)
        cond_val = self._to_bool(cond_val)
        self.builder.cbranch(cond_val, body_bb, exit_bb)

        # Body block
        self.builder.position_at_end(body_bb)
        self._gen_block(node.body)
        if not self.builder.block.is_terminated:
            self.builder.branch(cond_bb)   # back-edge

        self.builder.position_at_end(exit_bb)

        self.break_stack.pop()
        self.continue_stack.pop()

    def _gen_return(self, node: ReturnStatement) -> None:
        if node.value is None:
            self.builder.ret_void()
        else:
            val          = self._gen_expr(node.value)
            # Coerce to the function's declared return type
            ret_type     = self.cur_func.type.pointee.return_type
            if not isinstance(ret_type, ir.VoidType):
                val = self._coerce(val, ret_type)
            self.builder.ret(val)

    # ─── Expressions ─────────────────────────────────────────────────────────

    def _gen_expr(self, node) -> ir.Value:
        if isinstance(node, NumberLiteral):
            return ir.Constant(self.i64, node.value)

        if isinstance(node, FloatLiteral):
            return ir.Constant(self.f64, node.value)

        if isinstance(node, BoolLiteral):
            return ir.Constant(self.i1, 1 if node.value else 0)

        if isinstance(node, EmptyLiteral):
            return ir.Constant(self.i8p, None)

        if isinstance(node, StringLiteral):
            return self._gen_string(node.value)

        if isinstance(node, Identifier):
            if node.name not in self.value_table:
                raise CodegenError(
                    f"Undefined variable '{node.name}' (line {node.line})"
                )
            return self.builder.load(self.value_table[node.name], node.name)

        if isinstance(node, BinaryExpression):
            return self._gen_binary(node)

        if isinstance(node, UnaryExpression):
            return self._gen_unary(node)

        if isinstance(node, FunctionCall):
            return self._gen_call(node)

        raise CodegenError(f"Unknown AST node type: {type(node).__name__}")

    def _gen_string(self, text: str) -> ir.Value:
        """Emit a global null-terminated byte array and return an i8* pointer to it."""
        encoded  = (text + '\x00').encode('utf-8')
        arr_type = ir.ArrayType(self.i8, len(encoded))
        gv       = ir.GlobalVariable(self.module, arr_type,
                                     name=f'.jk_str.{self._str_idx}')
        self._str_idx     += 1
        gv.global_constant = True
        gv.linkage         = 'internal'
        gv.initializer     = ir.Constant(arr_type, bytearray(encoded))
        # GEP to get i8* pointing to element 0
        zero = ir.Constant(self.i32, 0)
        return self.builder.gep(gv, [zero, zero], inbounds=True, name='strptr')

    def _gen_binary(self, node: BinaryExpression) -> ir.Value:
        op    = node.operator
        left  = self._gen_expr(node.left)
        right = self._gen_expr(node.right)

        # String comparison: use strcmp when both operands are pointers
        if op in ('is', 'isnt') and isinstance(left.type, ir.PointerType):
            cmp = self.builder.call(
                self.func_table['strcmp'], [left, right], 'strcmpres'
            )
            zero = ir.Constant(self.i32, 0)
            eq   = self.builder.icmp_signed('==', cmp, zero, 'streq')
            return eq if op == 'is' else self.builder.not_(eq, 'strne')

        # Promote integer to float when one side is float
        is_float = isinstance(left.type, ir.DoubleType) or isinstance(right.type, ir.DoubleType)
        if is_float:
            left  = self._to_float(left)
            right = self._to_float(right)

        if op == '+':
            return (self.builder.fadd(left, right, 'faddtmp') if is_float
                    else self.builder.add(left, right, 'addtmp'))
        if op == '-':
            return (self.builder.fsub(left, right, 'fsubtmp') if is_float
                    else self.builder.sub(left, right, 'subtmp'))
        if op == '*':
            return (self.builder.fmul(left, right, 'fmultmp') if is_float
                    else self.builder.mul(left, right, 'multmp'))
        if op == '/':
            return (self.builder.fdiv(left, right, 'fdivtmp') if is_float
                    else self.builder.sdiv(left, right, 'divtmp'))
        if op == 'mod':
            return self.builder.srem(left, right, 'modtmp')
        if op == 'is':
            return (self.builder.fcmp_ordered('==', left, right, 'feq') if is_float
                    else self.builder.icmp_signed('==', left, right, 'ieq'))
        if op == 'isnt':
            return (self.builder.fcmp_ordered('!=', left, right, 'fne') if is_float
                    else self.builder.icmp_signed('!=', left, right, 'ine'))
        if op == 'gt':
            return (self.builder.fcmp_ordered('>', left, right, 'fgt') if is_float
                    else self.builder.icmp_signed('>', left, right, 'igt'))
        if op == 'lt':
            return (self.builder.fcmp_ordered('<', left, right, 'flt') if is_float
                    else self.builder.icmp_signed('<', left, right, 'ilt'))
        if op == 'gte':
            return (self.builder.fcmp_ordered('>=', left, right, 'fgte') if is_float
                    else self.builder.icmp_signed('>=', left, right, 'igte'))
        if op == 'lte':
            return (self.builder.fcmp_ordered('<=', left, right, 'flte') if is_float
                    else self.builder.icmp_signed('<=', left, right, 'ilte'))
        if op == 'also':
            return self.builder.and_(left, right, 'andtmp')
        if op == 'or':
            return self.builder.or_(left, right, 'ortmp')

        raise CodegenError(f"Unknown binary operator: '{op}'")

    def _gen_unary(self, node: UnaryExpression) -> ir.Value:
        operand = self._gen_expr(node.operand)
        if node.operator == 'flip':
            # XOR with 1 on i1 is a logical NOT
            return self.builder.xor(operand, ir.Constant(self.i1, 1), 'fliptmp')
        if node.operator == '-':
            if isinstance(operand.type, ir.DoubleType):
                return self.builder.fsub(ir.Constant(self.f64, 0.0), operand, 'fnegtmp')
            return self.builder.sub(ir.Constant(self.i64, 0), operand, 'negtmp')
        raise CodegenError(f"Unknown unary operator: '{node.operator}'")

    def _gen_call(self, node: FunctionCall) -> ir.Value:
        if node.name not in self.func_table:
            raise CodegenError(
                f"Undefined function '{node.name}' (line {node.line})"
            )
        fn   = self.func_table[node.name]
        args = [self._gen_expr(a) for a in node.arguments]

        # Coerce each argument to the declared parameter type
        fn_params = fn.type.pointee.args
        coerced   = []
        for i, arg in enumerate(args):
            if i < len(fn_params):
                coerced.append(self._coerce(arg, fn_params[i]))
            else:
                coerced.append(arg)

        ret_type = fn.type.pointee.return_type
        name     = '' if isinstance(ret_type, ir.VoidType) else 'calltmp'
        return self.builder.call(fn, coerced, name)

    # ─── Type coercion utilities ─────────────────────────────────────────────

    def _coerce(self, val: ir.Value, target: ir.Type) -> ir.Value:
        """Convert val to target type if needed (int↔float, i1 widening, etc.)."""
        src = val.type
        if src == target:
            return val
        if isinstance(target, ir.DoubleType) and isinstance(src, ir.IntType):
            return self.builder.sitofp(val, self.f64, 'tofloat')
        if isinstance(target, ir.IntType) and isinstance(src, ir.DoubleType):
            return self.builder.fptosi(val, target, 'toint')
        if isinstance(target, ir.IntType) and isinstance(src, ir.IntType):
            if target.width > src.width:
                return self.builder.zext(val, target, 'zext')
            if target.width < src.width:
                return self.builder.trunc(val, target, 'trunc')
        return val   # best effort — let LLVM's verifier catch real mismatches

    def _to_float(self, val: ir.Value) -> ir.Value:
        if isinstance(val.type, ir.DoubleType):
            return val
        return self.builder.sitofp(val, self.f64, 'tofloat')

    def _to_bool(self, val: ir.Value) -> ir.Value:
        """Ensure val is an i1 (for use as a branch condition)."""
        if isinstance(val.type, ir.IntType) and val.type.width == 1:
            return val
        return self.builder.icmp_signed(
            '!=', val, ir.Constant(val.type, 0), 'tobool'
        )
