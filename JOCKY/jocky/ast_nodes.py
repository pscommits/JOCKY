"""
ast_nodes.py — Abstract Syntax Tree node definitions for JOCKY.

Every grammatical construct in JOCKY is represented as a dataclass.
These are pure data containers — they hold the structure of the parsed
program.  The semantic analyser and code generator walk these trees.

'inferred_type' fields are filled in during semantic analysis.
'llvm_alloca'  fields are filled in during code generation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Any


# ─── Top-level ────────────────────────────────────────────────────────────────

@dataclass
class Program:
    """Root node.  A JOCKY source file is a list of function definitions."""
    functions: list[FunctionDef]
    line: int = 0


@dataclass
class Param:
    """One parameter in a function signature:  name : type"""
    name:            str
    type_annotation: str   # 'num', 'dec', 'text', 'flag', 'raw', 'nothing'
    line:            int = 0


@dataclass
class FunctionDef:
    """func name(params) -> return_type { body }"""
    name:        str
    params:      list[Param]
    return_type: str
    body:        Block
    line:        int = 0


# ─── Statements ───────────────────────────────────────────────────────────────

@dataclass
class Block:
    """A brace-delimited sequence of statements: { stmt; stmt; ... }"""
    statements: list[Any]
    line:       int = 0


@dataclass
class VarDecl:
    """var name : type := initializer"""
    name:            str
    type_annotation: str
    initializer:     Any
    line:            int = 0
    inferred_type:   Optional[str] = None


@dataclass
class Assignment:
    """name <- value"""
    name:  str
    value: Any
    line:  int = 0


@dataclass
class IfStatement:
    """check (condition) { then_body } otherwise { else_body }"""
    condition: Any
    then_body: Block
    else_body: Optional[Block]   # None when there is no 'otherwise' clause
    line:      int = 0


@dataclass
class LoopStatement:
    """loop (condition) { body }"""
    condition: Any
    body:      Block
    line:      int = 0


@dataclass
class ReturnStatement:
    """give [value]"""
    value: Optional[Any]   # None for 'give' with no expression (void return)
    line:  int = 0


@dataclass
class BreakStatement:
    """stop  — exits the innermost loop"""
    line: int = 0


@dataclass
class SkipStatement:
    """skip  — jumps to the next loop iteration"""
    line: int = 0


@dataclass
class ExpressionStatement:
    """An expression used as a statement (typically a function call)."""
    expression: Any
    line:       int = 0


# ─── Expressions ──────────────────────────────────────────────────────────────

@dataclass
class BinaryExpression:
    """left OP right  (e.g.  x + y,  a is b,  p also q)"""
    left:          Any
    operator:      str   # '+', '-', '*', '/', 'mod', 'is', 'isnt', 'gt', etc.
    right:         Any
    line:          int = 0
    inferred_type: Optional[str] = None


@dataclass
class UnaryExpression:
    """OP operand  (e.g.  flip x,  -y)"""
    operator:      str   # 'flip' or '-'
    operand:       Any
    line:          int = 0
    inferred_type: Optional[str] = None


@dataclass
class FunctionCall:
    """name(arg1, arg2, ...)"""
    name:          str
    arguments:     list[Any]
    line:          int = 0
    inferred_type: Optional[str] = None


@dataclass
class Identifier:
    """A reference to a variable by name."""
    name:          str
    line:          int = 0
    inferred_type: Optional[str] = None


@dataclass
class NumberLiteral:
    """An integer literal:  42"""
    value:         int
    line:          int = 0
    inferred_type: str = 'num'


@dataclass
class FloatLiteral:
    """A floating-point literal:  3.14"""
    value:         float
    line:          int = 0
    inferred_type: str = 'dec'


@dataclass
class StringLiteral:
    """A string literal enclosed in backticks:  `hello world`"""
    value:         str
    line:          int = 0
    inferred_type: str = 'text'


@dataclass
class BoolLiteral:
    """yes  or  no"""
    value:         bool
    line:          int = 0
    inferred_type: str = 'flag'


@dataclass
class EmptyLiteral:
    """empty  — a null / void value"""
    line:          int = 0
    inferred_type: str = 'nothing'
