"""
parser.py — Stage 2 of the JOCKY compiler: Recursive Descent Parsing.

Takes the flat token list from the lexer and builds an Abstract Syntax Tree.

Input:  list[Token]
Output: Program  (root AST node)

Each grammar rule has its own method.  Methods call each other recursively to
handle nested constructs.  Operator precedence falls naturally from the call
hierarchy: lower-precedence operators are higher in the call stack.
"""

from .tokens import Token, TokenType
from .ast_nodes import (
    Program, FunctionDef, Param, Block,
    VarDecl, Assignment, IfStatement, LoopStatement,
    ReturnStatement, BreakStatement, SkipStatement, ExpressionStatement,
    BinaryExpression, UnaryExpression, FunctionCall,
    Identifier, NumberLiteral, FloatLiteral, StringLiteral,
    BoolLiteral, EmptyLiteral,
)


class ParseError(Exception):
    def __init__(self, message: str, line: int):
        super().__init__(f"Parse error at line {line}: {message}")
        self.line = line


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos    = 0

    # ─── Internal helpers ────────────────────────────────────────────────────

    def _current(self) -> Token:
        return self.tokens[self.pos]

    def _peek_type(self, offset: int = 0) -> TokenType:
        idx = self.pos + offset
        return self.tokens[idx].type if idx < len(self.tokens) else TokenType.EOF

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return tok

    def _expect(self, token_type: TokenType) -> Token:
        tok = self._current()
        if tok.type != token_type:
            raise ParseError(
                f"Expected {token_type.name}, got {tok.type.name} ({tok.value!r})",
                tok.line,
            )
        return self._advance()

    def _match(self, *types: TokenType) -> bool:
        return self._current().type in types

    # ─── Entry point ─────────────────────────────────────────────────────────

    def parse(self) -> Program:
        """Parse the entire token stream and return the root Program node."""
        functions = []
        while not self._match(TokenType.EOF):
            if self._match(TokenType.FUNC):
                functions.append(self._parse_function_def())
            else:
                tok = self._current()
                raise ParseError(
                    f"Expected 'func', got {tok.type.name} ({tok.value!r})",
                    tok.line,
                )
        return Program(functions=functions)

    # ─── Function definitions ────────────────────────────────────────────────

    def _parse_function_def(self) -> FunctionDef:
        line = self._current().line
        self._expect(TokenType.FUNC)
        name_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.LPAREN)

        params: list[Param] = []
        if not self._match(TokenType.RPAREN):
            params = self._parse_param_list()

        self._expect(TokenType.RPAREN)
        self._expect(TokenType.ARROW_R)
        return_type = self._parse_type()
        body        = self._parse_block()

        return FunctionDef(
            name=name_tok.value,
            params=params,
            return_type=return_type,
            body=body,
            line=line,
        )

    def _parse_param_list(self) -> list[Param]:
        params = [self._parse_param()]
        while self._match(TokenType.COMMA):
            self._advance()
            params.append(self._parse_param())
        return params

    def _parse_param(self) -> Param:
        line     = self._current().line
        name_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.COLON)
        type_str = self._parse_type()
        return Param(name=name_tok.value, type_annotation=type_str, line=line)

    def _parse_type(self) -> str:
        TYPE_MAP = {
            TokenType.NUM_TYPE:     'num',
            TokenType.DEC_TYPE:     'dec',
            TokenType.TEXT_TYPE:    'text',
            TokenType.FLAG_TYPE:    'flag',
            TokenType.RAW_TYPE:     'raw',
            TokenType.NOTHING_TYPE: 'nothing',
        }
        tok = self._current()
        if tok.type in TYPE_MAP:
            self._advance()
            return TYPE_MAP[tok.type]
        raise ParseError(
            f"Expected a type keyword (num/dec/text/flag/raw/nothing), "
            f"got {tok.type.name} ({tok.value!r})",
            tok.line,
        )

    # ─── Blocks and statements ───────────────────────────────────────────────

    def _parse_block(self) -> Block:
        line = self._current().line
        self._expect(TokenType.LBRACE)
        stmts = []
        while not self._match(TokenType.RBRACE, TokenType.EOF):
            stmts.append(self._parse_statement())
        self._expect(TokenType.RBRACE)
        return Block(statements=stmts, line=line)

    def _parse_statement(self):
        tok = self._current()

        if tok.type == TokenType.VAR:
            return self._parse_var_decl()

        if tok.type == TokenType.CHECK:
            return self._parse_if_statement()

        if tok.type == TokenType.LOOP:
            return self._parse_loop_statement()

        if tok.type == TokenType.GIVE:
            return self._parse_return_statement()

        if tok.type == TokenType.STOP:
            self._advance()
            return BreakStatement(line=tok.line)

        if tok.type == TokenType.SKIP:
            self._advance()
            return SkipStatement(line=tok.line)

        # Assignment: IDENTIFIER <- expr
        if (tok.type == TokenType.IDENTIFIER and
                self._peek_type(1) == TokenType.ARROW_L):
            return self._parse_assignment()

        # Everything else is an expression statement (function call, etc.)
        expr = self._parse_expression()
        return ExpressionStatement(expression=expr, line=tok.line)

    def _parse_var_decl(self) -> VarDecl:
        line = self._current().line
        self._expect(TokenType.VAR)
        name_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.COLON)
        type_str = self._parse_type()
        self._expect(TokenType.ASSIGN)       # :=
        init     = self._parse_expression()
        return VarDecl(
            name=name_tok.value,
            type_annotation=type_str,
            initializer=init,
            line=line,
        )

    def _parse_assignment(self) -> Assignment:
        line     = self._current().line
        name_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.ARROW_L)      # <-
        value    = self._parse_expression()
        return Assignment(name=name_tok.value, value=value, line=line)

    def _parse_if_statement(self) -> IfStatement:
        line = self._current().line
        self._expect(TokenType.CHECK)
        self._expect(TokenType.LPAREN)
        condition = self._parse_expression()
        self._expect(TokenType.RPAREN)
        then_body = self._parse_block()

        else_body = None
        if self._match(TokenType.OTHERWISE):
            self._advance()
            else_body = self._parse_block()

        return IfStatement(
            condition=condition,
            then_body=then_body,
            else_body=else_body,
            line=line,
        )

    def _parse_loop_statement(self) -> LoopStatement:
        line = self._current().line
        self._expect(TokenType.LOOP)
        self._expect(TokenType.LPAREN)
        condition = self._parse_expression()
        self._expect(TokenType.RPAREN)
        body      = self._parse_block()
        return LoopStatement(condition=condition, body=body, line=line)

    def _parse_return_statement(self) -> ReturnStatement:
        line = self._current().line
        self._expect(TokenType.GIVE)
        # If the next token is '}' or EOF, this is a void return
        if self._match(TokenType.RBRACE, TokenType.EOF):
            return ReturnStatement(value=None, line=line)
        value = self._parse_expression()
        return ReturnStatement(value=value, line=line)

    # ─── Expressions (lowest to highest precedence) ──────────────────────────

    def _parse_expression(self):
        return self._parse_logic()

    def _parse_logic(self):
        """Handles 'also' and 'or' — lowest precedence."""
        left = self._parse_comparison()
        while self._match(TokenType.ALSO, TokenType.OR):
            op_tok = self._advance()
            right  = self._parse_comparison()
            left   = BinaryExpression(
                left=left, operator=op_tok.value, right=right, line=op_tok.line
            )
        return left

    def _parse_comparison(self):
        """Handles is / isnt / gt / lt / gte / lte."""
        left = self._parse_arithmetic()
        if self._match(TokenType.IS, TokenType.ISNT,
                       TokenType.GT, TokenType.LT,
                       TokenType.GTE, TokenType.LTE):
            op_tok = self._advance()
            right  = self._parse_arithmetic()
            return BinaryExpression(
                left=left, operator=op_tok.value, right=right, line=op_tok.line
            )
        return left

    def _parse_arithmetic(self):
        """Handles + and -."""
        left = self._parse_term()
        while self._match(TokenType.PLUS, TokenType.MINUS):
            op_tok = self._advance()
            right  = self._parse_term()
            left   = BinaryExpression(
                left=left, operator=op_tok.value, right=right, line=op_tok.line
            )
        return left

    def _parse_term(self):
        """Handles * / mod (higher precedence than + -)."""
        left = self._parse_unary()
        while self._match(TokenType.STAR, TokenType.SLASH, TokenType.MOD):
            op_tok = self._advance()
            right  = self._parse_unary()
            left   = BinaryExpression(
                left=left, operator=op_tok.value, right=right, line=op_tok.line
            )
        return left

    def _parse_unary(self):
        """Handles 'flip' (logical NOT) and unary minus."""
        if self._match(TokenType.FLIP):
            op_tok  = self._advance()
            operand = self._parse_unary()
            return UnaryExpression(operator='flip', operand=operand, line=op_tok.line)
        if self._match(TokenType.MINUS):
            op_tok  = self._advance()
            operand = self._parse_unary()
            return UnaryExpression(operator='-', operand=operand, line=op_tok.line)
        return self._parse_primary()

    def _parse_primary(self):
        """Handles atoms: literals, identifiers, function calls, parentheses."""
        tok = self._current()

        if tok.type == TokenType.NUMBER:
            self._advance()
            return NumberLiteral(value=int(tok.value), line=tok.line)

        if tok.type == TokenType.FLOAT:
            self._advance()
            return FloatLiteral(value=float(tok.value), line=tok.line)

        if tok.type == TokenType.STRING:
            self._advance()
            return StringLiteral(value=tok.value, line=tok.line)

        if tok.type == TokenType.YES:
            self._advance()
            return BoolLiteral(value=True, line=tok.line)

        if tok.type == TokenType.NO:
            self._advance()
            return BoolLiteral(value=False, line=tok.line)

        if tok.type == TokenType.EMPTY:
            self._advance()
            return EmptyLiteral(line=tok.line)

        # Identifier or function call
        if tok.type == TokenType.IDENTIFIER:
            if self._peek_type(1) == TokenType.LPAREN:
                return self._parse_function_call()
            self._advance()
            return Identifier(name=tok.value, line=tok.line)

        # Parenthesised expression
        if tok.type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_expression()
            self._expect(TokenType.RPAREN)
            return expr

        raise ParseError(
            f"Unexpected token {tok.type.name} ({tok.value!r}) in expression",
            tok.line,
        )

    def _parse_function_call(self) -> FunctionCall:
        line     = self._current().line
        name_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.LPAREN)
        args: list = []
        if not self._match(TokenType.RPAREN):
            args.append(self._parse_expression())
            while self._match(TokenType.COMMA):
                self._advance()
                args.append(self._parse_expression())
        self._expect(TokenType.RPAREN)
        return FunctionCall(name=name_tok.value, arguments=args, line=line)
