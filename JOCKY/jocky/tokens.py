"""
tokens.py — Token type definitions for the JOCKY language.

Every word, symbol, and value that the lexer can recognise is represented as
a TokenType enum value.  The keyword map translates a raw string like "func"
into its corresponding token type.
"""

from enum import Enum, auto


class TokenType(Enum):
    # ── Keywords ────────────────────────────────────────────────────────────
    FUNC        = auto()   # func
    VAR         = auto()   # var
    CHECK       = auto()   # check  (if)
    OTHERWISE   = auto()   # otherwise  (else)
    LOOP        = auto()   # loop  (while)
    GIVE        = auto()   # give  (return)
    STOP        = auto()   # stop  (break)
    SKIP        = auto()   # skip  (continue)
    YES         = auto()   # yes   (true)
    NO          = auto()   # no    (false)
    EMPTY       = auto()   # empty (null)

    # ── Type keywords ───────────────────────────────────────────────────────
    NUM_TYPE     = auto()  # num     (64-bit integer)
    DEC_TYPE     = auto()  # dec     (64-bit float)
    TEXT_TYPE    = auto()  # text    (string / char*)
    FLAG_TYPE    = auto()  # flag    (boolean)
    RAW_TYPE     = auto()  # raw     (byte buffer / void*)
    NOTHING_TYPE = auto()  # nothing (void)

    # ── Comparison operators (word form) ────────────────────────────────────
    IS   = auto()  # is   (==)
    ISNT = auto()  # isnt (!=)
    GT   = auto()  # gt   (>)
    LT   = auto()  # lt   (<)
    GTE  = auto()  # gte  (>=)
    LTE  = auto()  # lte  (<=)

    # ── Logical operators (word form) ────────────────────────────────────────
    ALSO = auto()  # also (&&)
    OR   = auto()  # or   (||)
    FLIP = auto()  # flip (!)

    # ── Arithmetic keyword operator ──────────────────────────────────────────
    MOD  = auto()  # mod  (%)

    # ── Literals ─────────────────────────────────────────────────────────────
    NUMBER     = auto()  # e.g. 42, 1000
    FLOAT      = auto()  # e.g. 3.14, -0.5
    STRING     = auto()  # e.g. `hello world`  (backtick-delimited)

    # ── Identifier ───────────────────────────────────────────────────────────
    IDENTIFIER = auto()  # any name that is not a keyword

    # ── Operators / Punctuation ──────────────────────────────────────────────
    ASSIGN   = auto()  # :=
    ARROW_L  = auto()  # <-
    ARROW_R  = auto()  # ->
    PLUS     = auto()  # +
    MINUS    = auto()  # -
    STAR     = auto()  # *
    SLASH    = auto()  # /
    LPAREN   = auto()  # (
    RPAREN   = auto()  # )
    LBRACE   = auto()  # {
    RBRACE   = auto()  # }
    COLON    = auto()  # :
    COMMA    = auto()  # ,

    # ── Special ──────────────────────────────────────────────────────────────
    EOF   = auto()  # end of file — signals the parser to stop
    ERROR = auto()  # invalid character — carries an error message in .value


# Maps raw keyword strings to their TokenType.
# When the lexer collects a word like "func", it checks this dictionary.
KEYWORDS: dict[str, TokenType] = {
    "func":      TokenType.FUNC,
    "var":       TokenType.VAR,
    "check":     TokenType.CHECK,
    "otherwise": TokenType.OTHERWISE,
    "loop":      TokenType.LOOP,
    "give":      TokenType.GIVE,
    "stop":      TokenType.STOP,
    "skip":      TokenType.SKIP,
    "yes":       TokenType.YES,
    "no":        TokenType.NO,
    "empty":     TokenType.EMPTY,
    "num":       TokenType.NUM_TYPE,
    "dec":       TokenType.DEC_TYPE,
    "text":      TokenType.TEXT_TYPE,
    "flag":      TokenType.FLAG_TYPE,
    "raw":       TokenType.RAW_TYPE,
    "nothing":   TokenType.NOTHING_TYPE,
    "is":        TokenType.IS,
    "isnt":      TokenType.ISNT,
    "gt":        TokenType.GT,
    "lt":        TokenType.LT,
    "gte":       TokenType.GTE,
    "lte":       TokenType.LTE,
    "also":      TokenType.ALSO,
    "or":        TokenType.OR,
    "flip":      TokenType.FLIP,
    "mod":       TokenType.MOD,
}


class Token:
    """One unit of JOCKY source text: its type, raw text value, and source location."""

    __slots__ = ('type', 'value', 'line', 'column')

    def __init__(self, type: TokenType, value: str, line: int, column: int):
        self.type   = type
        self.value  = value
        self.line   = line
        self.column = column

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, L{self.line}:C{self.column})"
