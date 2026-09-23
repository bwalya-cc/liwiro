// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class VersaEnumValue {
    private final String name;
    private final List<VersaEnumMemberValue> members = new ArrayList<>();
    private final Map<String, VersaEnumMemberValue> membersByName = new LinkedHashMap<>();

    public VersaEnumValue(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }

    public VersaEnumMemberValue addMember(String memberName, Object value, int ordinal) {
        VersaEnumMemberValue member = new VersaEnumMemberValue(this, memberName, value, ordinal);
        members.add(member);
        membersByName.put(memberName, member);
        return member;
    }

    public boolean hasMember(String memberName) {
        return membersByName.containsKey(memberName);
    }

    public VersaEnumMemberValue getMember(String memberName) {
        return membersByName.get(memberName);
    }

    public List<VersaEnumMemberValue> members() {
        return Collections.unmodifiableList(members);
    }

    public List<String> names() {
        List<String> names = new ArrayList<>(members.size());
        for (VersaEnumMemberValue member : members) {
            names.add(member.getName());
        }
        return names;
    }

    public List<Object> values() {
        List<Object> values = new ArrayList<>(members.size());
        for (VersaEnumMemberValue member : members) {
            values.add(member.getValue());
        }
        return values;
    }

    public Map<String, VersaEnumMemberValue> asMap() {
        return Collections.unmodifiableMap(membersByName);
    }

    @Override
    public String toString() {
        return "<enum " + name + ">";
    }
}
