// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

import java.util.Map;

public class AstImplementer implements AstVisitor<Void> {

    @Override
    public Void visitStringLiteral(StringLiteralNode node) {
        System.out.println("String Literal: " + node.getValue());
        return null;
    }

    @Override
    public Void visitNumber(NumberNode node) {
        System.out.println("Number: " + node.value);
        return null;
    }

    @Override
    public Void visitInteger(IntegerNode node) {
        System.out.println("Integer: " + node.value);
        return null;
    }

    @Override
    public Void visitIdentifier(IdentifierNode node) {
        System.out.println("Identifier: " + node.name);
        return null;
    }

    @Override
    public Void visitBinaryOperation(BinaryOperationNode node) {
        System.out.println("Binary Operation: " + node.operator);
        node.left.accept(this);
        node.right.accept(this);
        return null;
    }

    @Override
    public Void visitConditionalExpression(ConditionalExpressionNode node) {
        System.out.println("Conditional Expression");
        node.condition.accept(this);
        node.trueBranch.accept(this);
        node.falseBranch.accept(this);
        return null;
    }

    @Override
    public Void visitBlock(BlockNode node) {
        System.out.println("Block with " + node.statements.size() + " statements");
        for (Node statement : node.statements) {
            statement.accept(this);
        }
        return null;
    }

    @Override
    public Void visitFunctionDeclaration(FunctionDeclarationNode node) {
        System.out.println("Function Declaration: " + node.name);
        node.body.accept(this);
        return null;
    }

    @Override
    public Void visitCallExpression(CallExpressionNode node) {
        System.out.println("Call Expression");
        node.getCallee().accept(this);
        for (Node arg : node.getArguments()) {
            arg.accept(this);
        }
        return null;
    }

    @Override
    public Void visitIfStatement(IfStatementNode node) {
        System.out.println("If Statement");
        node.condition.accept(this);
        node.thenBranch.accept(this);
        if (node.elseBranch != null) node.elseBranch.accept(this);
        return null;
    }

    @Override
    public Void visitForLoop(ForLoopNode node) {
        System.out.println("For Loop");
        if (node.initializer != null) node.initializer.accept(this);
        if (node.condition != null) node.condition.accept(this);
        if (node.increment != null) node.increment.accept(this);
        node.body.accept(this);
        return null;
    }

    @Override
    public Void visitWhileLoop(WhileLoopNode node) {
        System.out.println("While Loop");
        node.condition.accept(this);
        node.body.accept(this);
        return null;
    }

    @Override
    public Void visitMatchStatement(MatchStatementNode node) {
        System.out.println("Match Statement");
        node.expression.accept(this);
        for (MatchCaseNode caseNode : node.cases) {
            caseNode.accept(this);
        }
        if (node.defaultCase != null) node.defaultCase.accept(this);
        return null;
    }

    @Override
    public Void visitListExpression(ListExpressionNode node) {
        System.out.println("List Expression with " + node.elements.size() + " elements");
        for (Node element : node.elements) {
            element.accept(this);
        }
        return null;
    }

    @Override
    public Void visitTupleExpression(TupleExpressionNode node) {
        System.out.println("Tuple Expression with " + node.elements.size() + " elements");
        for (Node element : node.elements) {
            element.accept(this);
        }
        return null;
    }

    @Override
    public Void visitObjectLiteral(ObjectLiteralNode node) {
        System.out.println("Object Literal with " + node.properties.size() + " properties");
        for (Map.Entry<String, Node> entry : node.properties.entrySet()) {
            System.out.println("Property: " + entry.getKey());
            entry.getValue().accept(this);
        }
        return null;
    }

    @Override
    public Void visitIndexAccess(IndexAccessNode node) {
        System.out.println("Index Access");
        node.getTarget().accept(this);
        node.getIndex().accept(this);
        return null;
    }

    @Override
    public Void visitIndexAccessNode(IndexAccessNode node) {
        System.out.println("Index Access");
        node.getTarget().accept(this);
        node.getIndex().accept(this);
        return null;
    }

    @Override
    public Void visitClassDeclaration(ClassDeclarationNode node) {
        System.out.println("Class Declaration: " + node.className);
        if (node.parent != null) node.parent.accept(this);
        node.body.accept(this);
        return null;
    }

    @Override
    public Void visitEnumDeclaration(EnumDeclarationNode node) {
        System.out.println("Enum Declaration: " + node.enumName);
        for (EnumMemberNode member : node.members) {
            member.accept(this);
        }
        return null;
    }

    @Override
    public Void visitEnumMember(EnumMemberNode node) {
        System.out.println("Enum Member: " + node.name + " (" + node.ordinal + ")");
        if (node.value != null) {
            node.value.accept(this);
        }
        return null;
    }

    @Override
    public Void visitMemberAccess(MemberAccessNode node) {
        System.out.println("Member Access: " + node.member);
        node.object.accept(this);
        return null;
    }

    @Override
    public Void visitNewInstance(NewInstanceNode node) {
        System.out.println("New Instance: " + node.className);
        for (Node arg : node.arguments) {
            arg.accept(this);
        }
        return null;
    }

    @Override
    public Void visitVariableDeclaration(VariableDeclarationNode node) {
        System.out.println("Variable Declaration: " + node.name);
        if (node.initializer != null) node.initializer.accept(this);
        return null;
    }

    @Override
    public Void visitConstantDeclaration(ConstantDeclarationNode node) {
        System.out.println("Constant Declaration: " + node.name);
        if (node.value != null) node.value.accept(this);
        return null;
    }

    @Override
    public Void visitReturnStatement(ReturnStatementNode node) {
        System.out.println("Return Statement");
        if (node.expression != null) node.expression.accept(this);
        return null;
    }

    @Override
    public Void visitDictionaryComprehension(DictionaryComprehensionNode node) {
        System.out.println("Dictionary Comprehension");
        System.out.println("Key Expression:");
        node.keyExpr.accept(this);
        System.out.println("Value Expression:");
        node.valueExpr.accept(this);
        System.out.println("Iterable:");
        node.iterable.accept(this);
        if (node.condition != null) {
            System.out.println("Condition:");
            node.condition.accept(this);
        }
        return null;
    }

    @Override
    public Void visitListComprehension(ListComprehensionNode node) {
        System.out.println("List Comprehension");
        System.out.println("Expression:");
        node.expression.accept(this);
        for (ComprehensionClause clause : node.getClauses()) {
            System.out.println("Clause Iterator: " + clause.iterator);
            System.out.println("Clause Iterable:");
            clause.iterable.accept(this);
            if (clause.condition != null) {
                System.out.println("Clause Condition:");
                clause.condition.accept(this);
            }
        }
        return null;
    }

    @Override
    public Void visitFloat(FloatNode node) {
        System.out.println("Float: " + node.value);
        return null;
    }

    @Override
    public Void visitBreakStatement(BreakStatementNode node) {
        System.out.println("Break Statement");
        return null;
    }

    @Override
    public Void visitContinueStatement(ContinueStatementNode node) {
        System.out.println("Continue Statement");
        return null;
    }

    @Override
    public Void visitFormattedString(FormattedStringNode node) {
        System.out.println("Formatted String with " + node.getParts().size() + " parts");
        for (Node part : node.getParts()) {
            part.accept(this);
        }
        return null;
    }

    @Override
    public Void visitElseIfClause(ElseIfClauseNode node) {
        System.out.println("Else If Clause");
        node.condition.accept(this);
        node.body.accept(this);
        return null;
    }

    @Override
    public Void visitNamedArgument(NamedArgumentNode node) {
        System.out.println("Named Argument");
        node.key.accept(this);
        node.value.accept(this);
        return null;
    }

    @Override
    public Void visitNoOp(NoOpNode node) {
        System.out.println("No Operation");
        return null;
    }

    @Override
    public Void visitStringNode(StringNode node) {
        System.out.println("String: " + node.value);
        return null;
    }

    @Override
    public Void visitUnaryOperation(UnaryOperationNode node) {
        System.out.println("Unary Operation: " + node.operator);
        node.operand.accept(this);
        return null;
    }

    @Override
    public Void visitParameter(ParameterNode node) {
        System.out.println("Parameter: " + node.name + " : " + node.type);
        return null;
    }

    @Override
    public Void visitMatchCase(MatchCaseNode node) {
        System.out.println("Match Case");
        System.out.println("Pattern:");
        node.pattern.accept(this);
        System.out.println("Body:");
        node.body.accept(this);
        return null;
    }

    @Override
    public Void visitForEachLoop(ForEachLoopNode node) {
        System.out.println("For Each Loop");
        System.out.println("Variable:");
        node.variable.accept(this);
        System.out.println("Iterable:");
        node.iterable.accept(this);
        System.out.println("Body:");
        node.body.accept(this);
        return null;
    }

    @Override
    public Void visitRangeList(RangeListNode node) {
        System.out.println("Range List: ");
        node.getStart().accept(this);
        node.getEnd().accept(this);
        return null;
    }

    @Override
    public Void visitThrowStatement(ThrowStatementNode node) {
        System.out.println("Throw Statement");
        node.expression.accept(this);
        return null;
    }

    @Override
    public Void visitBoolean(BooleanNode node) {
        System.out.println("Boolean: " + node.value);
        return null;
    }

    @Override
    public Void visitExpressionStatement(ExpressionStatementNode node) {
        System.out.println("Expression Statement: " + node.expression);
        node.expression.accept(this);
        return null;
    }

    @Override
    public Void visitLambdaExpression(LambdaExpressionNode node) {
        System.out.println("Lambda Expression:");
        for (ParameterNode param : node.parameters) {
            param.accept(this);
        }
        System.out.println("Body:");
        node.body.accept(this);
        return null;
    }
    
    @Override
    public Void visitTryCatch(TryCatchNode node) {
        System.out.println("Try Block:");
        node.tryBlock.accept(this);
        if (node.catchBlock != null) {
            System.out.println("Catch Block:");
            node.catchBlock.accept(this);
        }
        return null;
    }
}
