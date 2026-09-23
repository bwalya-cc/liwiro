// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import java.util.concurrent.atomic.AtomicInteger;
import com.google.gson.Gson;

public class ScriptDocument {
    private static final AtomicInteger idCounter = new AtomicInteger(1);
    private static final Gson gson = new Gson();
    
    public final String id;
    public String name;
    public String serviceName;
    public String code;
    public String language;
    public String extension;
    public long timestamp;
    public long lastEdited;

    public ScriptDocument(String name, String serviceName, String code) {
        this(name, serviceName, code, "Versa", ".versa");
    }

    public ScriptDocument(String name, String serviceName, String code, String language, String extension) {
        this.id = String.valueOf(idCounter.getAndIncrement());
        this.name = name;
        this.serviceName = serviceName;
        this.code = code;
        this.language = language;
        this.extension = extension;
        this.timestamp = System.currentTimeMillis();
        this.lastEdited = this.timestamp;
    }
    
    public void updateCode(String newCode) {
        this.code = newCode;
        this.lastEdited = System.currentTimeMillis();
    }
    
    public String getCode() {
        return code;
    }
    
    public String toJSON() {
        return gson.toJson(this);
    }
    
    @Override
    public String toString() {
        return toJSON();
    }
}
