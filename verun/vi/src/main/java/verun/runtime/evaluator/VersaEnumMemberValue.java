// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

public final class VersaEnumMemberValue {
    private final VersaEnumValue owner;
    private final String name;
    private final Object value;
    private final int ordinal;

    public VersaEnumMemberValue(VersaEnumValue owner, String name, Object value, int ordinal) {
        this.owner = owner;
        this.name = name;
        this.value = value;
        this.ordinal = ordinal;
    }

    public VersaEnumValue getOwner() {
        return owner;
    }

    public String getEnumName() {
        return owner.getName();
    }

    public String getName() {
        return name;
    }

    public Object getValue() {
        return value;
    }

    public int getOrdinal() {
        return ordinal;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof VersaEnumMemberValue)) {
            return false;
        }
        VersaEnumMemberValue that = (VersaEnumMemberValue) other;
        return owner == that.owner && name.equals(that.name);
    }

    @Override
    public int hashCode() {
        return 31 * System.identityHashCode(owner) + name.hashCode();
    }

    @Override
    public String toString() {
        return getEnumName() + "." + name;
    }
}
