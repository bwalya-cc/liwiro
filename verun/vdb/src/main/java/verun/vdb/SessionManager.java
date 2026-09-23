// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import java.util.*;
import java.util.concurrent.*;
import java.util.stream.Collectors;

public class SessionManager {
    private final Map<String, Session> activeSessions = new ConcurrentHashMap<>();
    private final long sessionTimeoutMs = 30 * 60 * 1000; // 30 minutes
    private final ScheduledExecutorService cleaner = Executors.newSingleThreadScheduledExecutor();

    public SessionManager() {
        cleaner.scheduleAtFixedRate(this::cleanupExpiredSessions, 5, 5, TimeUnit.MINUTES);
    }

    public String createSession(User user) {
        String sessionId = UUID.randomUUID().toString();
        Session session = new Session(sessionId, user);
        activeSessions.put(sessionId, session);
        return sessionId;
    }

    public Session validateSession(String sessionId) {
        Session session = activeSessions.get(sessionId);
        if (session != null && !session.isExpired()) {
            session.refresh();
            return session;
        }
        return null;
    }

    private void cleanupExpiredSessions() {
        long currentTime = System.currentTimeMillis();
        activeSessions.entrySet().removeIf(entry -> {
            Session session = entry.getValue();
            return session.isExpired() || (currentTime - session.getLastAccessed()) > sessionTimeoutMs;
        });
    }

    public class Session {
        private final String id;
        private final User user;
        private String currentDomain;
        private String currentDB;
        private long creationTime;
        private long lastAccessed;

        public Session(String id, User user) {
            this.id = id;
            this.user = user;
            this.currentDomain = "default";
            this.currentDB = "main";
            this.creationTime = System.currentTimeMillis();
            this.lastAccessed = creationTime;
        }

        public void refresh() {
            this.lastAccessed = System.currentTimeMillis();
        }

        public boolean isExpired() {
            return (System.currentTimeMillis() - lastAccessed) > sessionTimeoutMs;
        }

        public String getId() {
            return id;
        }

        public User getUser() {
            return user;
        }

        public String getCurrentDomain() {
            return currentDomain;
        }

        public void setCurrentDomain(String currentDomain) {
            this.currentDomain = currentDomain;
        }

        public String getCurrentDB() {
            return currentDB;
        }

        public void setCurrentDB(String currentDB) {
            this.currentDB = currentDB;
        }

        public long getCreationTime() {
            return creationTime;
        }

        public long getLastAccessed() {
            return lastAccessed;
        }
    }
}