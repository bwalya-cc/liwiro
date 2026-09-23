package verun.runtime.evaluator;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;
import verun.runtime.ast.Node;
import verun.runtime.lexer.Lexer;
import verun.runtime.lexer.Token;
import verun.runtime.parser.Parser;

class ReduceBuiltinTest {
    @Test
    void reducesWithAndWithoutInitialValue() {
        assertEquals(10, evaluate("reduce((left, right) => left + right, [1, 2, 3, 4]);"));
        assertEquals(15, ((Number) evaluate("reduce((left, right) => left + right, [1, 2, 3], 9);")).intValue());
    }

    @Test
    void supportsStringAndMapIterables() {
        assertEquals("abc", evaluate("reduce((left, right) => left + right, \"abc\", \"\");"));
        assertEquals("ab", evaluate("reduce((left, right) => left + right, {a: 1, b: 2}, \"\");"));
    }

    @Test
    void rejectsEmptyIterableWithoutInitialValue() {
        assertThrows(RuntimeException.class, () -> evaluate("reduce((left, right) => left + right, []);"));
    }

    private Object evaluate(String source) {
        List<Token> tokens = new Lexer(source).tokenize();
        Node ast = new Parser(tokens, source).parse();
        return new Evaluator(false, tokens, source).evaluate(ast);
    }
}
