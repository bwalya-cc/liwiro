// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

public final class EntryValue {
    private final Object key;
    private Object value;

    public EntryValue(Object key, Object value) {
        this.key = key;
        this.value = value;
    }

    public Object key() {
        return key;
    }

    public Object value() {
        return value;
    }

    public void setValue(Object value) {
        this.value = value;
    }
}
