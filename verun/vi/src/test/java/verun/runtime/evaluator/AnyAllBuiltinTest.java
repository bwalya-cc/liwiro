package verun.runtime.evaluator;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;
import verun.runtime.ast.Node;
import verun.runtime.lexer.Lexer;
import verun.runtime.lexer.Token;
import verun.runtime.parser.Parser;

class AnyAllBuiltinTest {
    @Test
    void evaluatesPredicatesAcrossIterables() {
        assertEquals(true, evaluate("any([false, 0, 2]);"));
        assertEquals(false, evaluate("all([true, false]);"));
        assertEquals(true, evaluate("all(\"ab\");"));
        assertEquals(false, evaluate("any({});"));
    }

    @Test
    void followsEmptyIterableIdentityRules() {
        assertEquals(false, evaluate("any([]);"));
        assertEquals(true, evaluate("all([]);"));
    }

    @Test
    void rejectsNonIterableInput() {
        assertThrows(RuntimeException.class, () -> evaluate("any(42);"));
    }

    private Object evaluate(String source) {
        List<Token> tokens = new Lexer(source).tokenize();
        Node ast = new Parser(tokens, source).parse();
        return new Evaluator(false, tokens, source).evaluate(ast);
    }
}
