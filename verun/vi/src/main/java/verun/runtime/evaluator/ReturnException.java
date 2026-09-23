// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

public class ReturnException extends ControlFlowSignal {
    public final Object value;

    public ReturnException(Object value) {
        this.value = value;
    }
}
