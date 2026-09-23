// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

public abstract class ControlFlowSignal extends RuntimeException {
    protected ControlFlowSignal() {
        super(null, null, false, false);
    }
}
