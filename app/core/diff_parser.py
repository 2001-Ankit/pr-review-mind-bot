from dataclasses import dataclass
from typing import List


@dataclass
class Hunk:
    header: str
    raw_lines: List[str]
    added_lines: List[str]
    removed_lines: List[str]
    context_lines: List[str]


@dataclass
class FileChange:
    file_name: str
    hunks: List[Hunk]
    total_added: int
    total_removed: int
    is_deleted:bool = False
    is_new:bool = False


class DiffParser:
    def parse(self, diff: str) -> List[FileChange]:
        lines = diff.splitlines()
        files = []

        current_file = None
        current_hunk = None

        for line in lines:

            if line.startswith("diff --git"):
                if current_file:
                    files.append(current_file)

                parts = line.split()
                b_path = parts[3] if len(parts) >= 4 else ""
                file_name = b_path[2:] if b_path.startswith("b/") else b_path

                current_file = FileChange(
                    file_name=file_name,
                    hunks=[],
                    total_added=0,
                    total_removed=0,
                )
                current_hunk = None

            elif current_file and line.startswith("new file mode"):
                current_file.is_new = True

            elif current_file and line.startswith("deleted file mode"):
                current_file.is_deleted = True

            elif line.startswith("@@") and current_file:
                current_hunk = Hunk(
                    header=line,
                    added_lines=[],
                    removed_lines=[],
                    context_lines=[],
                    raw_lines=[],
                )
                current_file.hunks.append(current_hunk)

            elif current_hunk:
                current_hunk.raw_lines.append(line)

                if line.startswith("+") and not line.startswith("+++"):
                    current_hunk.added_lines.append(line[1:])
                    current_file.total_added += 1

                elif line.startswith("-") and not line.startswith("---"):
                    current_hunk.removed_lines.append(line[1:])
                    current_file.total_removed += 1

                elif line.startswith(" "):
                    current_hunk.context_lines.append(line[1:])

        if current_file:
            files.append(current_file)

        return files

if __name__ == "__main__":
    parser = DiffParser()

    diff_text = """
iff --git a/.changeset/feat-manual-notation.md b/.changeset/feat-manual-notation.md
new file mode 100644
index 0000000..1bdf2ba
--- /dev/null
+++ b/.changeset/feat-manual-notation.md
@@ -0,0 +1,5 @@
+---
+"@googleworkspace/cli": minor
+---
+
+Add [MANUAL] notation to help text and runtime messages for steps requiring human interaction
diff --git a/skills/gws-shared/SKILL.md b/skills/gws-shared/SKILL.md
index c73285d..4efaff1 100644
--- a/skills/gws-shared/SKILL.md
+++ b/skills/gws-shared/SKILL.md
@@ -18,10 +18,10 @@ The `gws` binary must be on `$PATH`. See the project README for install options.
 ## Authentication

 ```bash
-# Browser-based OAuth (interactive)
+# [MANUAL] Browser-based OAuth (interactive — opens browser for consent)
 gws auth login

-# Service Account
+# Service Account (no manual interaction required)
 export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
 ```

diff --git a/src/auth_commands.rs b/src/auth_commands.rs
index 852190a..b46843e 100644
--- a/src/auth_commands.rs
+++ b/src/auth_commands.rs
@@ -116,12 +116,12 @@ fn token_cache_path() -> PathBuf {
 pub async fn handle_auth_command(args: &[String]) -> Result<(), GwsError> {
     const USAGE: &str = concat!(
         "Usage: gws auth <login|setup|status|export|logout>\n\n",
-        "  login   Authenticate via OAuth2 (opens browser)\n",
+        "  login   [MANUAL] Authenticate via OAuth2 (opens browser for consent)\n",
         "          --readonly   Request read-only scopes\n",
         "          --full       Request all scopes incl. pubsub + cloud-platform\n",
         "                       (may trigger restricted_client for unverified apps)\n",
         "          --scopes     Comma-separated custom scopes\n",
-        "  setup   Configure GCP project + OAuth client (requires gcloud)\n",
+        "  setup   [MANUAL] Configure GCP project + OAuth client (requires gcloud)\n",
         "          --project    Use a specific GCP project\n",
         "  status  Show current authentication state\n",
         "  export  Print decrypted credentials to stdout\n",
@@ -159,7 +159,7 @@ impl yup_oauth2::authenticator_delegate::InstalledFlowDelegate for CliFlowDelega
     ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<String, String>> + Send + 'a>>
     {
         Box::pin(async move {
-            eprintln!("Open this URL in your browser to authenticate:\n");
+            eprintln!("[MANUAL] Open this URL in your browser to authenticate:\n");
             eprintln!("  {url}\n");
             Ok(String::new())
         })
@@ -341,8 +341,8 @@ fn resolve_client_credentials() -> Result<(String, String, Option<String>), GwsE
         Err(_) => Err(GwsError::Auth(
             "No OAuth client configured.\n\n\
              Either:\n  \
-               1. Run `gws auth setup` to configure a GCP project and OAuth client\n  \
-               2. Download client_secret.json from Google Cloud Console and save it to:\n     \
+               1. [MANUAL] Run `gws auth setup` (interactive wizard, opens browser)\n  \
+               2. [MANUAL] Download client_secret.json from Google Cloud Console and save it to:\n     \       
                   ~/.config/gws/client_secret.json\n  \
                3. Set env vars: GOOGLE_WORKSPACE_CLI_CLIENT_ID and GOOGLE_WORKSPACE_CLI_CLIENT_SECRET"
                 .to_string(),
diff --git a/src/error.rs b/src/error.rs
index 25cc9f5..c68e350 100644
--- a/src/error.rs
+++ b/src/error.rs
@@ -111,11 +111,11 @@ pub fn print_error_json(err: &GwsError) {
     {
         if reason == "accessNotConfigured" {
             eprintln!();
-            eprintln!("💡 API not enabled for your GCP project.");
+            eprintln!("💡 [MANUAL] API not enabled for your GCP project.");
             if let Some(url) = enable_url {
-                eprintln!("   Enable it at: {url}");
+                eprintln!("   [MANUAL] Enable it at: {url}");
             } else {
-                eprintln!("   Visit the GCP Console → APIs & Services → Library to enable the required API."); 
+                eprintln!("   [MANUAL] Visit the GCP Console → APIs & Services → Library to enable the required API.");
             }
             eprintln!("   After enabling, wait a few seconds and retry your command.");
         }
diff --git a/src/setup.rs b/src/setup.rs
index b5757fa..46b28b0 100644
--- a/src/setup.rs
+++ b/src/setup.rs
@@ -907,7 +907,7 @@ fn stage_account(ctx: &mut SetupContext) -> Result<SetupStage, GwsError> {
                             .unwrap()
                             .suspend()
                             .map_err(|e| GwsError::Validation(format!("TUI error: {e}")))?;
-                        eprintln!("  → Opening browser for login...");
+                        eprintln!("  → [MANUAL] Opening browser for login...");
                         gcloud_auth_login()?;
                         let acct = get_gcloud_account()?.ok_or_else(|| {
                             GwsError::Auth("Authentication failed — no active account".to_string())
@@ -1237,21 +1237,21 @@ fn manual_oauth_instructions(project_id: &str) -> String {

     format!(
         concat!(
-            "OAuth client creation requires manual setup in the Google Cloud Console.\n\n",
+            "[MANUAL] OAuth client creation requires manual setup in the Google Cloud Console.\n\n",
             "Follow these steps:\n\n",
-            "1. Configure the OAuth consent screen (if not already done):\n",
+            "1. [MANUAL] Configure the OAuth consent screen (if not already done):\n",
             "   {consent_url}\n",
             "   → User Type: External\n",
             "   → App name: gws CLI (or your preferred name)\n",
             "   → Support email: your Google account email\n",
             "   → Save and continue through all screens\n\n",
-            "2. Create an OAuth client ID:\n",
+            "2. [MANUAL] Create an OAuth client ID:\n",
             "   {creds_url}\n",
             "   → Click 'Create Credentials' → 'OAuth client ID'\n",
             "   → Application type: Desktop app\n",
             "   → Name: gws CLI (or your preferred name)\n",
             "   → Click 'Create'\n\n",
-            "3. Copy the Client ID and Client Secret shown in the dialog.\n\n",
+            "3. [MANUAL] Copy the Client ID and Client Secret shown in the dialog.\n\n",
             "4. Provide the credentials to gws using one of these methods:\n\n",
             "   Option A — Environment variables (recommended for CI/scripts):\n",
             "     export GOOGLE_WORKSPACE_CLI_CLIENT_ID=\"<your-client-id>\"\n",

diff --git a/.changeset/feat-manual-notation.md b/.changeset/feat-manual-notation.md
new file mode 100644
index 0000000..1bdf2ba
--- /dev/null
+++ b/.changeset/feat-manual-notation.md
@@ -0,0 +1,5 @@
+---
+"@googleworkspace/cli": minor
+---
+
+Add [MANUAL] notation to help text and runtime messages for steps requiring human interaction
diff --git a/skills/gws-shared/SKILL.md b/skills/gws-shared/SKILL.md
index c73285d..4efaff1 100644
--- a/skills/gws-shared/SKILL.md
+++ b/skills/gws-shared/SKILL.md
@@ -18,10 +18,10 @@ The `gws` binary must be on `$PATH`. See the project README for install options.
 ## Authentication

 ```bash
-# Browser-based OAuth (interactive)
+# [MANUAL] Browser-based OAuth (interactive — opens browser for consent)
 gws auth login

-# Service Account
+# Service Account (no manual interaction required)
 export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
 ```

diff --git a/src/auth_commands.rs b/src/auth_commands.rs
index 852190a..b46843e 100644
--- a/src/auth_commands.rs
+++ b/src/auth_commands.rs
@@ -116,12 +116,12 @@ fn token_cache_path() -> PathBuf {
 pub async fn handle_auth_command(args: &[String]) -> Result<(), GwsError> {
     const USAGE: &str = concat!(
         "Usage: gws auth <login|setup|status|export|logout>\n\n",
-        "  login   Authenticate via OAuth2 (opens browser)\n",
+        "  login   [MANUAL] Authenticate via OAuth2 (opens browser for consent)\n",
         "          --readonly   Request read-only scopes\n",
         "          --full       Request all scopes incl. pubsub + cloud-platform\n",
         "                       (may trigger restricted_client for unverified apps)\n",
         "          --scopes     Comma-separated custom scopes\n",
-        "  setup   Configure GCP project + OAuth client (requires gcloud)\n",
+        "  setup   [MANUAL] Configure GCP project + OAuth client (requires gcloud)\n",
         "          --project    Use a specific GCP project\n",
         "  status  Show current authentication state\n",
         "  export  Print decrypted credentials to stdout\n",
@@ -159,7 +159,7 @@ impl yup_oauth2::authenticator_delegate::InstalledFlowDelegate for CliFlowDelega
     ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<String, String>> + Send + 'a>>
     {
         Box::pin(async move {
-            eprintln!("Open this URL in your browser to authenticate:\n");
+            eprintln!("[MANUAL] Open this URL in your browser to authenticate:\n");
             eprintln!("  {url}\n");
             Ok(String::new())
         })
@@ -341,8 +341,8 @@ fn resolve_client_credentials() -> Result<(String, String, Option<String>), GwsE
         Err(_) => Err(GwsError::Auth(
             "No OAuth client configured.\n\n\
              Either:\n  \
-               1. Run `gws auth setup` to configure a GCP project and OAuth client\n  \
-               2. Download client_secret.json from Google Cloud Console and save it to:\n     \
+               1. [MANUAL] Run `gws auth setup` (interactive wizard, opens browser)\n  \
+               2. [MANUAL] Download client_secret.json from Google Cloud Console and save it to:\n     \       
                   ~/.config/gws/client_secret.json\n  \
                3. Set env vars: GOOGLE_WORKSPACE_CLI_CLIENT_ID and GOOGLE_WORKSPACE_CLI_CLIENT_SECRET"
                 .to_string(),
diff --git a/src/error.rs b/src/error.rs
index 25cc9f5..c68e350 100644
--- a/src/error.rs
+++ b/src/error.rs
@@ -111,11 +111,11 @@ pub fn print_error_json(err: &GwsError) {
     {
         if reason == "accessNotConfigured" {
             eprintln!();
-            eprintln!("💡 API not enabled for your GCP project.");
+            eprintln!("💡 [MANUAL] API not enabled for your GCP project.");
             if let Some(url) = enable_url {
-                eprintln!("   Enable it at: {url}");
+                eprintln!("   [MANUAL] Enable it at: {url}");
             } else {
-                eprintln!("   Visit the GCP Console → APIs & Services → Library to enable the required API."); 
+                eprintln!("   [MANUAL] Visit the GCP Console → APIs & Services → Library to enable the required API.");
             }
             eprintln!("   After enabling, wait a few seconds and retry your command.");
         }
diff --git a/src/setup.rs b/src/setup.rs
index b5757fa..46b28b0 100644
--- a/src/setup.rs
+++ b/src/setup.rs
@@ -907,7 +907,7 @@ fn stage_account(ctx: &mut SetupContext) -> Result<SetupStage, GwsError> {
                             .unwrap()
                             .suspend()
                             .map_err(|e| GwsError::Validation(format!("TUI error: {e}")))?;
-                        eprintln!("  → Opening browser for login...");
+                        eprintln!("  → [MANUAL] Opening browser for login...");
                         gcloud_auth_login()?;
                         let acct = get_gcloud_account()?.ok_or_else(|| {
                             GwsError::Auth("Authentication failed — no active account".to_string())
@@ -1237,21 +1237,21 @@ fn manual_oauth_instructions(project_id: &str) -> String {

     format!(
         concat!(
-            "OAuth client creation requires manual setup in the Google Cloud Console.\n\n",
+            "[MANUAL] OAuth client creation requires manual setup in the Google Cloud Console.\n\n",
             "Follow these steps:\n\n",
-            "1. Configure the OAuth consent screen (if not already done):\n",
+            "1. [MANUAL] Configure the OAuth consent screen (if not already done):\n",
             "   {consent_url}\n",
             "   → User Type: External\n",
             "   → App name: gws CLI (or your preferred name)\n",
             "   → Support email: your Google account email\n",
             "   → Save and continue through all screens\n\n",
-            "2. Create an OAuth client ID:\n",
+            "2. [MANUAL] Create an OAuth client ID:\n",
             "   {creds_url}\n",
             "   → Click 'Create Credentials' → 'OAuth client ID'\n",
             "   → Application type: Desktop app\n",
             "   → Name: gws CLI (or your preferred name)\n",
             "   → Click 'Create'\n\n",
-            "3. Copy the Client ID and Client Secret shown in the dialog.\n\n",
+            "3. [MANUAL] Copy the Client ID and Client Secret shown in the dialog.\n\n",
             "4. Provide the credentials to gws using one of these methods:\n\n",
             "   Option A — Environment variables (recommended for CI/scripts):\n",
             "     export GOOGLE_WORKSPACE_CLI_CLIENT_ID=\"<your-client-id>\"\n",

"""

    files = parser.parse(diff_text)
    
    for file in files:
        print("File:", file.file_name)
        print("Added:", file.total_added)
        print("Removed:", file.total_removed)
        print("Hunks:", len(file.hunks))
        print("all hunks",file.hunks)