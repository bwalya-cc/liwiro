// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import java.io.IOException;
import com.google.gson.JsonSyntaxException;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import java.util.Scanner;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import java.util.Collections;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.nio.file.*;
import verun.common.JsonValueConverter;

public class VDBConsole {
    // ANSI Color Codes
    private static final String ANSI_RESET = "\u001B[0m";
    private static final String ANSI_BLUE = "\u001B[34m";
    private static final String ANSI_CYAN = "\u001B[36m";
    private static final String ANSI_GREEN = "\u001B[32m";
    private static final String ANSI_YELLOW = "\u001B[33m";
    private static final String ANSI_RED = "\u001B[31m";
    private static final String RESET = "\u001B[0m";
    private static VDBLogger logger;

    public static void main(String[] args) {
        VDBLogSettings.setRuntimeLogsEnabled(true);
        VDB.setRuntimeLogsEnabled(true);
        Scanner scanner = new Scanner(System.in);
        try {
            DirectoryUtil.ensureDirectories();
            MitLicense.initialize();
            if (!MitLicense.ensureConsoleAcceptance(scanner, "console")) {
                System.out.println(ANSI_RED + "MIT license not accepted. Exiting." + ANSI_RESET);
                scanner.close();
                System.exit(1);
            }
            logger = new VDBLogger(DirectoryUtil.sessionId);
            VDB.initialize(); // Initial initialization
        } catch (IllegalStateException e) {
            System.out.println(ANSI_RED + "Super admin not configured. Creating initial admin..." + ANSI_RESET);
            VDB.checkSuperAdmin();
        } catch (IOException e) {
            System.err.println("Directory initialization failed: " + e.getMessage());
        }
    
        if (logger == null) {
            try {
                DirectoryUtil.ensureDirectories();
                logger = DirectoryUtil.logger;
            } catch (Exception e) {
                System.err.println("Logger initialization failed: " + e.getMessage());
            }
        }
    
        User authenticatedUser;
        if (args.length >= 2) {
            authenticatedUser = authenticateUser(args[0], args[1]);
        } else {
            authenticatedUser = authenticateUserInteractively(scanner);
        }
    
        VDB.setCurrentUser(authenticatedUser);
    
        VDB.initialize(); // Now runs with valid user context
        VQLProcessor processor = new VQLProcessor(authenticatedUser, "default");
    
        // Check if there is input available to determine batch mode
        boolean hasInput = false;
        try {
            hasInput = System.in.available() > 0;
        } catch (IOException e) {
            System.err.println("Error checking input availability: " + e.getMessage());
        }

        try {
            boolean interactiveAdvisor = System.console() != null && !hasInput;
            IndexAdvisor.startupAdvisor("convo", interactiveAdvisor);
        } catch (Exception e) {
            System.err.println("Index advisor startup check failed: " + e.getMessage());
        }
    
        if (hasInput) {
            processBatchInput(processor, scanner);
        } else {
            if (System.console() != null) {
                try (VDBLineEditor editor = new VDBLineEditor()) {
                    runInteractiveMode(processor, editor);
                }
            } else {
                System.out.println("No input provided. Exiting.");
            }
        }
        scanner.close();
    }
    
    private static User authenticateUserInteractively(Scanner scanner) {
        UserManager userManager = UserManager.getInstance();
        
        // Check if this is first-time setup
        if (userManager.listUsers().isEmpty()) {
            System.out.println("\u001B[33mFirst-time setup: No users found.\u001B[0m");
            return createFirstUser(scanner, userManager);
        }
        
        System.out.println("\u001B[34mVersaDB Console Login\u001B[0m");
        
        for (int tries = 3; tries > 0; tries--) {
            try {
                System.out.print("\u001B[36mUsername: \u001B[0m");
                String username = User.normalizeUsername(scanner.nextLine());
                
                String password = readPasswordInput(scanner, "\u001B[36mPassword: \u001B[0m");
                
                User user = userManager.getUser(username);
                if (user != null && password != null && user.authenticate(password)) {
                    VDB.setCurrentUser(user);
                    System.out.println("\u001B[32mAuthentication successful\u001B[0m");
                    return user;
                }
                
                System.out.println("\u001B[31mInvalid credentials. Attempts remaining: " + (tries - 1) + "\u001B[0m");
                
            } catch (Exception e) {
                System.out.println("\u001B[31mAuthentication error: " + e.getMessage() + "\u001B[0m");
                System.out.println("\u001B[31mAttempts remaining: " + (tries - 1) + "\u001B[0m");
            }
        }
        
        System.out.println("\u001B[31mMaximum authentication attempts exceeded. Please try again.\u001B[0m");
        scanner.close();
        System.exit(1);
        return null; // unreachable
    }
    
    private static User createFirstUser(Scanner scanner, UserManager userManager) {
        System.out.println("\u001B[36mCreating first administrator account...\u001B[0m");
        
        try {
            System.out.print("\u001B[36mEnter username: \u001B[0m");
            String username = User.normalizeUsername(scanner.nextLine());
            
            System.out.print("\u001B[36mEnter email: \u001B[0m");
            String email = scanner.nextLine();
            
            String password = readPasswordInput(scanner, "\u001B[36mEnter password: \u001B[0m");
            
            // Validate input
            if (username == null || username.trim().isEmpty()) {
                System.out.println("\u001B[31mUsername cannot be empty\u001B[0m");
                System.exit(1);
            }
            
            if (email == null || email.trim().isEmpty()) {
                System.out.println("\u001B[31mEmail cannot be empty\u001B[0m");
                System.exit(1);
            }
            
            if (password == null || password.trim().isEmpty()) {
                System.out.println("\u001B[31mPassword cannot be empty\u001B[0m");
                System.exit(1);
            }
            
            // Create the first user as SUPER_ADMIN directly to bypass UserManager restrictions
            User firstUser = new User(username, email.trim(), "SUPER_ADMIN", password);
            
            // Save user directly to file
            saveFirstUser(firstUser);
            
            // Add to UserManager's in-memory cache
            userManager.addUser(firstUser);
            
            // Initialize the system with this user
            VDB.setCurrentUser(firstUser);
            
            // Create default domain and database
            VDB.defineDomain("default", "main", true);
            
            System.out.println("\u001B[32mFirst user created successfully!\u001B[0m");
            System.out.println("\u001B[32mAuthentication successful\u001B[0m");
            
            return firstUser;
            
        } catch (Exception e) {
            System.out.println("\u001B[31mError creating first user: " + e.getMessage() + "\u001B[0m");
            System.exit(1);
            return null;
        }
    }
    
    private static void saveFirstUser(User user) throws IOException {
        Path userFilePath = DirectoryUtil.getUsersStorePath();
        Files.createDirectories(userFilePath.getParent());
        
        Gson gson = new GsonBuilder()
            .registerTypeAdapter(User.class, new User.UserSerializer())
            .create();
            
        List<User> users = Arrays.asList(user);
        BsonStorage.writeValue(userFilePath, JsonValueConverter.convertViaJson(gson, users));
    }
    
    private static User authenticateUser(String username, String password) {
        User user = UserManager.getInstance().getUser(User.normalizeUsername(username));
        if (user != null && password != null && user.authenticate(password)) {
            VDB.setCurrentUser(user);
            System.out.println("\u001B[32mAuthentication successful\u001B[0m");
            return user;
        }
        
        System.out.println("\u001B[31mInvalid credentials\u001B[0m");
        System.exit(1);
        return null; // unreachable
    }

    private static String readPasswordInput(Scanner scanner, String prompt) {
        java.io.Console console = System.console();
        if (console != null) {
            char[] secret = console.readPassword(prompt);
            return secret == null ? "" : new String(secret);
        }
        System.out.print(prompt);
        return scanner.nextLine();
    }

    private static void runInteractiveMode(VQLProcessor processor, Scanner scanner) {
        processor.setInterface("CONSOLE");
        while (true) {
            System.out.printf(ANSI_BLUE + "vdb:%s/%s> " + ANSI_RESET,
                    processor.currentDomain, processor.currentDB);

            if (!scanner.hasNextLine()) {
                break;
            }

            String input = scanner.nextLine().trim();
            if (input.endsWith(";")) {
                input = input.substring(0, input.length() - 1).trim();
            }

            if (input.equalsIgnoreCase("exit")) {
                break;
            }
            if (isClearCommand(input)) {
                clearConsole();
                continue;
            }
            if (handleLicenseCommand(input)) {
                continue;
            }
            String[] helpParts = input.split("\\s+", 2);
            if (helpParts.length > 0 && "help".equalsIgnoreCase(helpParts[0])) {
                String topic = helpParts.length > 1 ? helpParts[1].trim() : "";
                printHelp(processor, topic);
                continue;
            }

            String response = processor.executeReadableCommand(input);
            if (!response.isEmpty()) {
                System.out.println(colorizeJson(response));
            }
        }
    }

    /** Interactive mode backed by the readline-style editor (arrow keys/history/etc.). */
    private static void runInteractiveMode(VQLProcessor processor, VDBLineEditor editor) {
        processor.setInterface("CONSOLE");
        String helpTopic = "";
        int helpPage = 1;
        while (true) {
            String input;
            try {
                input = editor.readLine(String.format(ANSI_BLUE + "vdb:%s/%s> " + ANSI_RESET,
                        processor.currentDomain, processor.currentDB));
            } catch (IOException e) {
                System.out.println(errorResponse("Console input failed: " + e.getMessage()));
                break;
            }
            if (input == null) break;
            if (VDBLineEditor.HELP_NEXT.equals(input) || VDBLineEditor.HELP_PREVIOUS.equals(input)) {
                int delta = VDBLineEditor.HELP_NEXT.equals(input) ? 1 : -1;
                helpPage = Math.max(1, helpPage + delta);
                printHelp(processor, helpTopic + " " + helpPage);
                editor.setPageNavigation(true);
                continue;
            }
            editor.setPageNavigation(false);
            input = input.trim();
            if (input.endsWith(";")) input = input.substring(0, input.length() - 1).trim();
            if (input.equalsIgnoreCase("exit") || input.equalsIgnoreCase("quit")) break;
            if (isClearCommand(input)) { clearConsole(); continue; }
            if (handleLicenseCommand(input)) continue;
            String[] helpParts = input.split("\\s+", 2);
            if (helpParts.length > 0 && "help".equalsIgnoreCase(helpParts[0])) {
                helpTopic = helpParts.length > 1 ? helpParts[1].trim() : "";
                helpPage = 1;
                printHelp(processor, helpTopic);
                editor.setPageNavigation(true);
                continue;
            }
            String response = processor.executeReadableCommand(input);
            if (!response.isEmpty()) System.out.println(colorizeJson(response));
        }
    }

    private static boolean handleLicenseCommand(String input) {
        if (input == null) {
            return false;
        }
        String normalized = input.trim();
        if (normalized.isEmpty()) {
            return false;
        }
        String lower = normalized.toLowerCase();
        boolean commandMatch = lower.equals("license") || lower.equals("licence")
                || lower.startsWith("license ") || lower.startsWith("licence ")
                || lower.startsWith("liscence ");
        if (!commandMatch) {
            return false;
        }
        System.out.println(ANSI_CYAN + "License" + ANSI_RESET);
        System.out.println(colorizeJson(new GsonBuilder().setPrettyPrinting().create().toJson(MitLicense.licenseDisclosure())));
        return true;
    }

    static boolean isClearCommand(String input) {
        if (input == null) {
            return false;
        }
        String normalized = input.trim().toLowerCase();
        return "clear".equals(normalized) || "cls".equals(normalized);
    }

    static void clearConsole() {
        // Home, erase the visible display, and erase saved lines (terminal scrollback).
        System.out.print("\033[H\033[2J\033[3J");
        System.out.flush();
    }

    private static void processBatchInput(VQLProcessor processor, Scanner scanner) {
        StringBuilder statements = new StringBuilder();
        while (scanner.hasNextLine()) statements.append(scanner.nextLine()).append('\n');
        System.out.println(colorizeJson(processor.executeReadableCommand(statements.toString())));
    }

    private static void printWelcome() {
        System.out.println(ANSI_GREEN + "Welcome to VersaDB - Type 'help' for commands" + ANSI_RESET);
    }

    private static void printHelp(VQLProcessor processor, String topic) {
        System.out.println(HelpProvider.getHelpText(topic == null ? "" : topic, processor.getCurrentUser(), processor.currentDomain, processor.currentDB));
    }

    private static String colorizeJson(String json) {
        // Simple JSON syntax highlighting
        return json.replaceAll("\"(\\w+)\":", ANSI_CYAN + "\"$1\":" + ANSI_RESET)
                .replaceAll(": \"(.*?)\"", ": " + ANSI_GREEN + "\"$1\"" + ANSI_RESET)
                .replaceAll(": (\\d+\\.?\\d*)", ": " + ANSI_YELLOW + "$1" + ANSI_RESET);
    }

    private static boolean isValidJson(String json) {
        try {
            new Gson().fromJson(json, Object.class);
            return true;
        } catch (JsonSyntaxException e) {
            return false;
        }
    }

    private static String errorResponse(String message) {
        return new Gson().toJson(Collections.singletonMap("error", message));
    }
}
