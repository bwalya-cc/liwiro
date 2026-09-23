// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: MIT

package verun.vdb;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Scanner;

public final class MitLicense {
    private static final String COPYRIGHT_OWNER = "Bwalya Cameron Chishimba";
    private static final String SOURCE_REPO = "https://zulan.io/folio/verun";

    private MitLicense() {
    }

    public static synchronized void initialize() {
        DirectoryUtil.ensureDirectories();
    }

    public static synchronized Path acceptanceFile() {
        initialize();
        return DirectoryUtil.SYS_DIR.resolve("mit-license-acceptance" + BsonStorage.DOCUMENT_EXTENSION);
    }

    public static synchronized boolean isAccepted() {
        return Files.isRegularFile(acceptanceFile());
    }

    public static synchronized boolean ensureConsoleAcceptance(Scanner scanner, String channel) {
        if (isAccepted()) {
            return true;
        }
        System.out.println("Verun + Liwiro is distributed under the MIT License.");
        System.out.print("Accept MIT license? [y/N]: ");
        if (scanner == null || !scanner.hasNextLine()) {
            return false;
        }
        String answer = scanner.nextLine().trim();
        if (!"y".equals(answer) && !"Y".equals(answer)) {
            return false;
        }
        recordAcceptance(resolveAcceptedBy(), channel);
        return true;
    }

    public static synchronized void requireAccepted(String channel) {
        if (!isAccepted()) {
            throw new IllegalStateException(
                    "MIT license not accepted. Run a VDB startup command in a terminal and answer y/Y first."
            );
        }
    }

    public static synchronized void recordAcceptance(String acceptedBy, String channel) {
        initialize();
        Map<String, Object> payload = new LinkedHashMap<String, Object>();
        payload.put("accepted", true);
        payload.put("license", "MIT");
        payload.put("spdx_license_expression", "MIT");
        payload.put("accepted_at", Instant.now().toString());
        payload.put("accepted_by", sanitize(acceptedBy, "unknown"));
        payload.put("channel", sanitize(channel, "unknown"));
        payload.put("source_repo", SOURCE_REPO);
        try {
            BsonStorage.writeDocument(acceptanceFile(), payload);
        } catch (IOException e) {
            throw new RuntimeException("Failed to record MIT license acceptance: " + e.getMessage(), e);
        }
    }

    public static synchronized Map<String, Object> licenseDisclosure() {
        Map<String, Object> out = new LinkedHashMap<String, Object>();
        out.put("title", "MIT License");
        out.put("spdx_license_expression", "MIT");
        out.put("license", "MIT");
        out.put("accepted", isAccepted());
        out.put("copyright_owner", COPYRIGHT_OWNER);
        out.put("source_repo", SOURCE_REPO);
        out.put("permissions", new String[]{
                "Use",
                "Copy",
                "Modify",
                "Merge",
                "Publish",
                "Distribute",
                "Sublicense",
                "Sell"
        });
        out.put("conditions", new String[]{
                "Include the copyright notice and MIT license text in substantial portions of the software."
        });
        out.put("limitations", new String[]{
                "Provided AS IS, without warranty of any kind."
        });
        out.put("acceptance_file", acceptanceFile().toString());
        return out;
    }

    public static synchronized Map<String, Object> health(String runtime) {
        Map<String, Object> out = new LinkedHashMap<String, Object>();
        out.put("status", "ok");
        out.put("runtime", sanitize(runtime, "VDB"));
        out.put("license", "MIT");
        out.put("spdx_license_expression", "MIT");
        out.put("accepted", isAccepted());
        return out;
    }

    private static String resolveAcceptedBy() {
        return sanitize(System.getProperty("user.name"), "unknown");
    }

    private static String sanitize(String value, String fallback) {
        String text = value == null ? "" : value.trim();
        return text.isEmpty() ? fallback : text;
    }
}
