// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public interface AstVisitor<T> {

    // Literals and Identifiers
    T visitStringLiteral(StringLiteralNode node);
    T visitNumber(NumberNode node);
    T visitInteger(IntegerNode node);
    T visitIdentifier(IdentifierNode node);

    // Basic Expressions
    T visitBinaryOperation(BinaryOperationNode node);
    T visitUnaryOperation(UnaryOperationNode node);
    T visitCallExpression(CallExpressionNode node);
    T visitLambdaExpression(LambdaExpressionNode node);
    T visitConditionalExpression(ConditionalExpressionNode node);
    T visitExpressionStatement(ExpressionStatementNode node);

    // Control Flow and Statements
    T visitBlock(BlockNode node);
    T visitIfStatement(IfStatementNode node);
    T visitForLoop(ForLoopNode node);
    T visitWhileLoop(WhileLoopNode node);
    T visitMatchStatement(MatchStatementNode node);
    T visitElseIfClause(ElseIfClauseNode node);
    T visitBreakStatement(BreakStatementNode node);
    T visitContinueStatement(ContinueStatementNode node);

    // Declarations
    T visitFunctionDeclaration(FunctionDeclarationNode node);
    T visitVariableDeclaration(VariableDeclarationNode node);
    T visitConstantDeclaration(ConstantDeclarationNode node);
    T visitReturnStatement(ReturnStatementNode node);
    T visitParameter(ParameterNode node);

    // Data Structures
    T visitListExpression(ListExpressionNode node);
    T visitTupleExpression(TupleExpressionNode node);
    T visitObjectLiteral(ObjectLiteralNode node);
    T visitIndexAccess(IndexAccessNode node);
    T visitRangeList(RangeListNode node);
    T visitDictionaryComprehension(DictionaryComprehensionNode node);
    T visitListComprehension(ListComprehensionNode node);

    // Object-Oriented Constructs
    T visitClassDeclaration(ClassDeclarationNode node);
    T visitEnumDeclaration(EnumDeclarationNode node);
    T visitEnumMember(EnumMemberNode node);
    T visitMemberAccess(MemberAccessNode node);
    T visitNewInstance(NewInstanceNode node);

    // Additional Constructs
    T visitFormattedString(FormattedStringNode node);
    T visitNamedArgument(NamedArgumentNode node);
    T visitNoOp(NoOpNode node);
    T visitStringNode(StringNode node);
    T visitMatchCase(MatchCaseNode node);
    T visitForEachLoop(ForEachLoopNode node);

    // Literal Extensions
    T visitFloat(FloatNode node);
    T visitBoolean(BooleanNode node);
    T visitTryCatch(TryCatchNode node);
    T visitThrowStatement(ThrowStatementNode node);

    T visitIndexAccessNode(IndexAccessNode node);
}
