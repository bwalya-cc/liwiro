// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import java.util.List;
import java.util.function.Function;

// In BuiltinFunction.java
public class BuiltinFunction implements Callable {
    private final Function<List<Object>, Object> function;

    public BuiltinFunction(Function<List<Object>, Object> function) {
        this.function = function;
    }

    @Override
    public Object call(List<Object> arguments) {
        return function.apply(arguments);
    }
}