package verun.runtime.evaluator;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;
import verun.runtime.ast.Node;
import verun.runtime.lexer.Lexer;
import verun.runtime.lexer.Token;
import verun.runtime.parser.Parser;

class SumBuiltinTest {
    @Test
    void sumsIntegerAndFloatingPointIterables() {
        assertEquals(10, evaluate("sum([1, 2, 3, 4]);"));
        assertEquals(10.5d, ((Number) evaluate("sum([1.5, 2, 3, 4], 0);")).doubleValue(), 0.000001d);
    }

    @Test
    void supportsAllLanguageIterablesAndRejectsNonNumericValues() {
        assertEquals(3, evaluate("sum(set(1, 2));"));
        assertThrows(RuntimeException.class, () -> evaluate("sum([1, \"two\"]);") );
    }

    private Object evaluate(String source) {
        List<Token> tokens = new Lexer(source).tokenize();
        Node ast = new Parser(tokens, source).parse();
        return new Evaluator(false, tokens, source).evaluate(ast);
    }
}
