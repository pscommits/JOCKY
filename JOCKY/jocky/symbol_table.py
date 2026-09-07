"""
symbol_table.py — Scope-aware name registry for the JOCKY compiler.

The symbol table is a stack of dictionaries.
- Each dictionary represents one scope level (function body, block, etc.).
- When a name is declared, it is added to the current (innermost) scope.
- When a name is looked up, the stack is searched from innermost to outermost.
- Entering a block pushes a new scope; leaving pops it.
"""


class SymbolError(Exception):
    pass


class Symbol:
    """Represents a declared variable or parameter."""
    def __init__(self, name: str, type_str: str, line: int, kind: str = 'variable'):
        self.name       = name
        self.type_str   = type_str
        self.line       = line
        self.kind       = kind          # 'variable' | 'parameter'
        self.llvm_alloca = None         # filled in by CodeGenerator


class FunctionSymbol:
    """Represents a declared function (user-defined or stdlib)."""
    def __init__(self, name: str, param_types: list[str],
                 return_type: str, line: int = -1):
        self.name        = name
        self.param_types = param_types  # list of type strings for each parameter
        self.return_type = return_type
        self.line        = line
        self.llvm_func   = None         # filled in by CodeGenerator


class SymbolTable:
    """
    A scoped symbol table.

    Variables live in scope stacks.
    Functions live in a flat dictionary (JOCKY does not allow nested functions).
    """

    def __init__(self):
        self._scopes:    list[dict[str, Symbol]] = [{}]   # index 0 = global scope
        self._functions: dict[str, FunctionSymbol]        = {}

    # ─── Scope control ────────────────────────────────────────────────────────

    def enter_scope(self) -> None:
        """Push a fresh scope onto the stack."""
        self._scopes.append({})

    def exit_scope(self) -> None:
        """Pop the innermost scope from the stack."""
        if len(self._scopes) > 1:
            self._scopes.pop()

    # ─── Variable declarations ────────────────────────────────────────────────

    def declare_var(self, name: str, type_str: str, line: int,
                    kind: str = 'variable') -> Symbol:
        """
        Add a variable to the current scope.
        Raises SymbolError if the name already exists in this exact scope.
        """
        current = self._scopes[-1]
        if name in current:
            raise SymbolError(
                f"Variable '{name}' already declared in this scope (line {line})"
            )
        sym = Symbol(name, type_str, line, kind)
        current[name] = sym
        return sym

    def lookup_var(self, name: str, line: int) -> Symbol:
        """
        Find a variable by name.  Searches from innermost to outermost scope.
        Raises SymbolError if not found anywhere.
        """
        for scope in reversed(self._scopes):
            if name in scope:
                return scope[name]
        raise SymbolError(f"Undefined variable '{name}' (line {line})")

    def in_current_scope(self, name: str) -> bool:
        return name in self._scopes[-1]

    # ─── Function declarations ────────────────────────────────────────────────

    def declare_function(self, name: str, param_types: list[str],
                         return_type: str, line: int = -1) -> FunctionSymbol:
        """Register a function.  Silently replaces if already exists (for stdlib pre-seeding)."""
        sym = FunctionSymbol(name, param_types, return_type, line)
        self._functions[name] = sym
        return sym

    def lookup_function(self, name: str, line: int) -> FunctionSymbol:
        if name in self._functions:
            return self._functions[name]
        raise SymbolError(f"Undefined function '{name}' (line {line})")

    def has_function(self, name: str) -> bool:
        return name in self._functions
