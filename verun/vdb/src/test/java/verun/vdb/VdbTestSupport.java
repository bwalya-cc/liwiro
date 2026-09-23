// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

final class VdbTestSupport {
    private VdbTestSupport() {
    }

    static User ensureBootstrappedSuperAdmin() {
        MitLicense.recordAcceptance("JUnit", "test");
        UserManager userManager = UserManager.getInstance();
        User superAdmin = userManager.getSuperAdmin();
        if (superAdmin == null) {
            superAdmin = new User("test_root", "test-root@local.test", "SUPER_ADMIN", "Aa1!aaaa");
            userManager.addUser(superAdmin);
        }

        VDB.setCurrentUser(superAdmin);
        if (!DirectoryUtil.domainExists("default") || !DirectoryUtil.dbExists("default", "main")) {
            VDB.defineDomain("default", "main", false);
        }
        VDB.setDomain("default");
        return superAdmin;
    }
}
