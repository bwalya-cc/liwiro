package verun.runtime.evaluator;

import java.util.List;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Locale;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class StringEvaluatorTest {
    @Test
    void separatorJoinConsumesListArgument() {
        assertEquals("alpha-beta-gamma",
                StringEvaluator.callMethod("join", "-", List.of(List.of("alpha", "beta", "gamma"))));
    }

    @Test
    void separatorJoinHandlesStringWithoutTrailingSeparator() {
        assertEquals("a-b-c", StringEvaluator.callMethod("join", "-", List.of("abc")));
    }

    @Test
    void separatorJoinPreservesSupplementaryUnicodeCodePoints() {
        assertEquals("😀-🚀", StringEvaluator.callMethod("join", "-", List.of("😀🚀")));
    }

    @Test
    void separatorJoinAcceptsSetsAndMapKeys() {
        assertEquals("a-b", StringEvaluator.callMethod("join", "-",
                List.of(new LinkedHashSet<>(List.of("a", "b")))));
        LinkedHashMap<String, Integer> values = new LinkedHashMap<>();
        values.put("first", 1);
        values.put("second", 2);
        assertEquals("first|second", StringEvaluator.callMethod("join", "|", List.of(values)));
    }

    @Test
    void joinRequiresAnIterableArgument() {
        assertThrows(EvaluationException.class,
                () -> StringEvaluator.callMethod("join", ",", List.of()));
    }

    @Test
    void splitWithoutDelimiterUsesRunsOfWhitespace() {
        assertEquals(List.of("alpha", "beta", "gamma"),
                StringEvaluator.callMethod("split", "  alpha\t beta\n gamma  ", List.of()));
    }

    @Test
    void stripVariantsHandleUnicodeWhitespace() {
        assertEquals("value", StringEvaluator.callMethod("strip", "\u2003value\u2003", List.of()));
        assertEquals("value", StringEvaluator.callMethod("lstrip", "\u2003value", List.of()));
        assertEquals("value", StringEvaluator.callMethod("rstrip", "value\u2003", List.of()));
    }

    @Test
    void caseConversionIsIndependentOfHostLocale() {
        Locale original = Locale.getDefault();
        try {
            Locale.setDefault(Locale.forLanguageTag("tr"));
            assertEquals("IDI", StringEvaluator.callMethod("upper", "idi", List.of()));
            assertEquals("i", StringEvaluator.callMethod("lower", "I", List.of()));
        } finally {
            Locale.setDefault(original);
        }
    }
}
