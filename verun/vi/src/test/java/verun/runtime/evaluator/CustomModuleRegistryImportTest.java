// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import org.junit.jupiter.api.Test;
import verun.runtime.Main;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class CustomModuleRegistryImportTest {

    @Test
    void directFileExecutionLoadsCustomModuleFromRegistry() throws Exception {
        Path registryDir = Files.createTempDirectory("vi-custom-modules");
        Path modulesDir = Files.createDirectories(registryDir.resolve("modules"));
        Files.writeString(
                modulesDir.resolve("greeter.versa"),
                "func hello(name) {\n  return \"hello \" + name;\n}\n"
        );
        Files.writeString(
                registryDir.resolve("registry.json"),
                "{\n" +
                        "  \"version\": 1,\n" +
                        "  \"modules\": [\n" +
                        "    {\n" +
                        "      \"name\": \"greeter\",\n" +
                        "      \"title\": \"Greeter\",\n" +
                        "      \"description\": \"Test module\",\n" +
                        "      \"scope\": \"domain\",\n" +
                        "      \"assigned_domains\": [\"portal\"],\n" +
                        "      \"owner_domains\": [\"portal\"],\n" +
                        "      \"config_schema\": {},\n" +
                        "      \"config_defaults\": {},\n" +
                        "      \"source_path\": \"modules/greeter.versa\"\n" +
                        "    }\n" +
                        "  ]\n" +
                        "}\n"
        );
        Path script = Files.createTempFile("vi-custom-module", ".versa");
        Files.writeString(
                script,
                "import greeter;\nprint(greeter.hello(\"zulan\"));\n"
        );

        String previousRegistry = System.getProperty("vi.custom.modules.dir");
        String previousDomain = System.getProperty("liwiro.versa.module.domain");
        PrintStream originalOut = System.out;
        ByteArrayOutputStream stdout = new ByteArrayOutputStream();
        try {
            System.setProperty("vi.custom.modules.dir", registryDir.toString());
            System.setProperty("liwiro.versa.module.domain", "portal");
            System.setOut(new PrintStream(stdout, true, StandardCharsets.UTF_8));
            Main.main(new String[]{script.toString(), "--msg-only"});
        } finally {
            if (previousRegistry == null) {
                System.clearProperty("vi.custom.modules.dir");
            } else {
                System.setProperty("vi.custom.modules.dir", previousRegistry);
            }
            if (previousDomain == null) {
                System.clearProperty("liwiro.versa.module.domain");
            } else {
                System.setProperty("liwiro.versa.module.domain", previousDomain);
            }
            System.setOut(originalOut);
        }

        String output = stdout.toString(StandardCharsets.UTF_8);
        assertTrue(output.contains("hello zulan"), output);
    }

    @Test
    void directFileExecutionLoadsSeededVdbModuleAndEnvWithoutLegacyRegistry() throws Exception {
        Path vdbRoot = Files.createTempDirectory("vi-vdb-root");
        Path emptyModuleDir = Files.createTempDirectory("vi-empty-modules");
        Path script = Files.createTempFile("vi-vdb-module", ".versa");
        Files.writeString(
                script,
                "import mediacloud;\n"
                        + "let status = mediacloud.status();\n"
                        + "print(status.providers.cloudinary.folder);\n"
                        + "print(env.PORTAL_KEY);\n"
        );

        ProcessBuilder processBuilder = new ProcessBuilder(
                "java",
                "-Dverun.vdb.root=" + vdbRoot,
                "-Dvi.custom.modules.dir=" + emptyModuleDir,
                "-cp",
                System.getProperty("java.class.path"),
                "verun.runtime.Main",
                script.toString(),
                "--msg-only"
        );
        processBuilder.redirectErrorStream(true);
        processBuilder.environment().put("CLOUDINARY_FOLDER", "portal-folder");
        processBuilder.environment().put("PORTAL_KEY", "portal-secret");

        Process process = processBuilder.start();
        assertTrue(process.waitFor(30, TimeUnit.SECONDS), "VI process did not finish in time");
        String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);

        assertEquals(0, process.exitValue(), output);
        assertTrue(output.contains("portal-folder"), output);
        assertTrue(output.contains("portal-secret"), output);
        assertTrue(
                Files.isRegularFile(
                        vdbRoot.resolve("__data__")
                                .resolve("domains")
                                .resolve("default")
                                .resolve("dbs")
                                .resolve("main")
                                .resolve("collections")
                                .resolve("modules")
                                .resolve("data")
                                .resolve("mediacloud.bson")
                ),
                "Expected the seeded VDB module document to be created"
        );
    }
}
