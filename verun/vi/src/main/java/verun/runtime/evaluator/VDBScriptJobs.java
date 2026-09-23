// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import verun.runtime.ast.Node;
import verun.runtime.lexer.Lexer;
import verun.runtime.lexer.Token;
import verun.runtime.parser.Parser;
import verun.vdb.ScriptDocument;
import verun.vdb.VDB;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;

final class VDBScriptJobs {
    private static final ScheduledExecutorService SCHEDULER = Executors.newScheduledThreadPool(1, new ThreadFactory() {
        @Override
        public Thread newThread(Runnable runnable) {
            Thread thread = new Thread(runnable, "vdb-script-jobs");
            thread.setDaemon(true);
            return thread;
        }
    });

    private static final Map<String, JobState> JOBS = new ConcurrentHashMap<>();
    private static final Map<String, ScheduledFuture<?>> FUTURES = new ConcurrentHashMap<>();

    private VDBScriptJobs() {
    }

    static synchronized Map<String, Object> scheduleJob(String name, String scriptName, long startAtMs, long everySeconds,
            Map<String, Object> params, Evaluator evaluator) {
        if (name == null || name.trim().isEmpty()) {
            throw new RuntimeException("Job name is required");
        }
        if (scriptName == null || scriptName.trim().isEmpty()) {
            throw new RuntimeException("Script name is required");
        }

        cancelJob(name);

        long now = System.currentTimeMillis();
        long initialDelayMs = Math.max(0L, startAtMs - now);
        long intervalSeconds = Math.max(1L, everySeconds);

        JobState state = new JobState(name, scriptName, intervalSeconds, startAtMs,
                params == null ? Collections.emptyMap() : new LinkedHashMap<>(params));
        JOBS.put(name, state);

        Runnable task = () -> runJob(state, evaluator);
        ScheduledFuture<?> future = SCHEDULER.scheduleAtFixedRate(task, initialDelayMs, intervalSeconds * 1000L,
                TimeUnit.MILLISECONDS);
        FUTURES.put(name, future);

        return state.toMap();
    }

    static synchronized boolean cancelJob(String name) {
        if (name == null || name.trim().isEmpty()) {
            return false;
        }
        ScheduledFuture<?> future = FUTURES.remove(name);
        JobState state = JOBS.remove(name);
        if (state != null) {
            state.status = "cancelled";
        }
        if (future != null) {
            future.cancel(false);
            return true;
        }
        return false;
    }

    static List<Map<String, Object>> listJobs() {
        List<Map<String, Object>> out = new ArrayList<>();
        for (JobState state : JOBS.values()) {
            out.add(state.toMap());
        }
        return out;
    }

    private static void runJob(JobState state, Evaluator parentEvaluator) {
        state.lastRunAtMs = System.currentTimeMillis();
        state.runCount += 1;
        state.status = "running";
        try {
            Object value = Evaluator.executeVdbScript(state.scriptName, () -> {
                ScriptDocument script = VDB.loadScript(state.scriptName);
                String code = script == null ? null : script.code;
                if (code == null || code.trim().isEmpty()) {
                    throw new RuntimeException("Script is empty: " + state.scriptName);
                }

                Lexer lexer = new Lexer(code);
                List<Token> tokens = lexer.tokenize();
                Parser parser = new Parser(tokens, code);
                Node ast = parser.parse();

                Evaluator nested = new Evaluator(parentEvaluator.getEnvironment());
                nested.getEnvironment().put("params", new LinkedHashMap<>(state.params));
                return nested.evaluate(ast);
            });
            state.lastResult = value;
            state.lastError = null;
            state.status = "scheduled";
        } catch (Exception e) {
            state.lastError = e.getMessage() == null ? e.toString() : e.getMessage();
            state.status = "error";
        }
    }

    private static final class JobState {
        private final String name;
        private final String scriptName;
        private final long everySeconds;
        private final long startAtMs;
        private final Map<String, Object> params;
        private volatile long runCount;
        private volatile long lastRunAtMs;
        private volatile Object lastResult;
        private volatile String lastError;
        private volatile String status;

        private JobState(String name, String scriptName, long everySeconds, long startAtMs, Map<String, Object> params) {
            this.name = name;
            this.scriptName = scriptName;
            this.everySeconds = everySeconds;
            this.startAtMs = startAtMs;
            this.params = params;
            this.status = "scheduled";
        }

        private Map<String, Object> toMap() {
            Map<String, Object> out = new LinkedHashMap<>();
            out.put("name", name);
            out.put("script", scriptName);
            out.put("every_seconds", everySeconds);
            out.put("start_at", startAtMs);
            out.put("status", status);
            out.put("run_count", runCount);
            out.put("last_run_at", lastRunAtMs == 0 ? null : lastRunAtMs);
            out.put("last_error", lastError);
            out.put("last_result", lastResult);
            out.put("params", new LinkedHashMap<>(params));
            return out;
        }
    }
}
