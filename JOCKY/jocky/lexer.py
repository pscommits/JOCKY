"""
lexer.py — Stage 1 of the JOCKY compiler: Lexical Analysis.

The lexer reads the raw text of a .jk source file character by character
and groups those characters into tokens — the 'words' of JOCKY.

Input:  A string containing the entire source file.
Output: A list of Token objects.
"""

from .tokens import Token, TokenType, KEYWORDS


class Lexer:
    """
    Walks the source string left-to-right, one character at a time,
    and emits Token objects into self.tokens.
    """

    def __init__(self, source: str):
        self.source  = source
        self.pos     = 0        # current index into self.source
        self.line    = 1        # 1-indexed line counter
        self.column  = 1        # 1-indexed column counter
        self.tokens: list[Token] = []

    # ─── Internal helpers ────────────────────────────────────────────────────

    def _current(self) -> str | None:
        """Return the character at self.pos without advancing, or None at EOF."""
        return self.source[self.pos] if self.pos < len(self.source) else None

    def _peek(self, offset: int = 1) -> str | None:
        """Look ahead by offset characters without advancing."""
        p = self.pos + offset
        return self.source[p] if p < len(self.source) else None

    def _advance(self) -> str:
        """Consume and return the current character, updating line/column."""
        ch = self.source[self.pos]
        self.pos += 1
        if ch == '\n':
            self.line  += 1
            self.column = 1
        else:
            self.column += 1
        return ch

    def _emit(self, token_type: TokenType, value: str,
              line: int, column: int) -> None:
        self.tokens.append(Token(token_type, value, line, column))

    # ─── Public entry point ──────────────────────────────────────────────────

    def tokenize(self) -> list[Token]:
        """
        Process the entire source and return the token list.
        Always ends with a TOKEN_EOF.
        """
        while self.pos < len(self.source):
            self._scan_one()
        self.tokens.append(Token(TokenType.EOF, '', self.line, self.column))
        return self.tokens

    # ─── Token scanning ──────────────────────────────────────────────────────

    def _scan_one(self) -> None:
        """Scan exactly one token starting at the current position."""
        start_line   = self.line
        start_column = self.column
        ch           = self._current()

        # ── Whitespace (skip silently) ───────────────────────────────────────
        if ch in (' ', '\t', '\r'):
            self._advance()
            return

        # ── Newlines (update position, no token emitted) ─────────────────────
        if ch == '\n':
            self._advance()
            return

        # ── Comments: ## ... (rest of line) ─────────────────────────────────
        if ch == '#' and self._peek() == '#':
            while self.pos < len(self.source) and self._current() != '\n':
                self._advance()
            return

        # ── Multi-character operators (must check before single-char) ─────────

        if ch == ':' and self._peek() == '=':
            self._advance(); self._advance()
            self._emit(TokenType.ASSIGN, ':=', start_line, start_column)
            return

        if ch == '<' and self._peek() == '-':
            self._advance(); self._advance()
            self._emit(TokenType.ARROW_L, '<-', start_line, start_column)
            return

        if ch == '-' and self._peek() == '>':
            self._advance(); self._advance()
            self._emit(TokenType.ARROW_R, '->', start_line, start_column)
            return

        # ── Single-character operators / punctuation ─────────────────────────
        SINGLE = {
            '+': TokenType.PLUS,
            '-': TokenType.MINUS,
            '*': TokenType.STAR,
            '/': TokenType.SLASH,
            '(': TokenType.LPAREN,
            ')': TokenType.RPAREN,
            '{': TokenType.LBRACE,
            '}': TokenType.RBRACE,
            ':': TokenType.COLON,
            ',': TokenType.COMMA,
        }
        if ch in SINGLE:
            self._advance()
            self._emit(SINGLE[ch], ch, start_line, start_column)
            return

        # ── String literals: `backtick-delimited` ────────────────────────────
        if ch == '`':
            self._advance()   # consume opening backtick
            chars = []
            while self.pos < len(self.source) and self._current() != '`':
                if self._current() == '\n':
                    self._emit(TokenType.ERROR,
                               'unterminated string literal (no closing backtick)',
                               start_line, start_column)
                    return
                chars.append(self._advance())
            if self.pos >= len(self.source):
                self._emit(TokenType.ERROR,
                           'unterminated string literal (reached end of file)',
                           start_line, start_column)
                return
            self._advance()   # consume closing backtick
            self._emit(TokenType.STRING, ''.join(chars), start_line, start_column)
            return

        # ── Number literals ───────────────────────────────────────────────────
        if ch is not None and ch.isdigit():
            digits    = []
            has_dot   = False
            while (self.pos < len(self.source) and
                   (self._current().isdigit() or
                    (self._current() == '.' and not has_dot and
                     self._peek() is not None and self._peek().isdigit()))):
                if self._current() == '.':
                    has_dot = True
                digits.append(self._advance())
            tok_type = TokenType.FLOAT if has_dot else TokenType.NUMBER
            self._emit(tok_type, ''.join(digits), start_line, start_column)
            return

        # ── Identifiers and keywords ──────────────────────────────────────────
        if ch is not None and (ch.isalpha() or ch == '_'):
            chars = []
            while (self.pos < len(self.source) and
                   (self._current().isalnum() or self._current() == '_')):
                chars.append(self._advance())
            word     = ''.join(chars)
            tok_type = KEYWORDS.get(word, TokenType.IDENTIFIER)
            self._emit(tok_type, word, start_line, start_column)
            return

        # ── Anything else is an error ─────────────────────────────────────────
        bad = self._advance()
        self._emit(TokenType.ERROR,
                   f"unexpected character '{bad}'",
                   start_line, start_column)
