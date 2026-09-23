// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import org.junit.jupiter.api.Test;
import verun.runtime.lexer.Lexer;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

class LexerRobustnessTest {
    @Test
    void reportsUnterminatedFormattedStringInsteadOfCrashingAtEof() {
        RuntimeException error = assertThrows(RuntimeException.class,
                () -> new Lexer("`unterminated").tokenize());
        org.junit.jupiter.api.Assertions.assertTrue(error.getMessage().contains("Unterminated formatted string"));
    }

    @Test
    void reportsUnterminatedInterpolation() {
        RuntimeException error = assertThrows(RuntimeException.class,
                () -> new Lexer("`hello {name`").tokenize());
        org.junit.jupiter.api.Assertions.assertTrue(error.getMessage().contains("Unterminated interpolation"));
    }

    @Test
    void acceptsClosedFormattedString() {
        assertDoesNotThrow(() -> new Lexer("`hello {name}`").tokenize());
    }
}
