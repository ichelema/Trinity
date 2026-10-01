# Secrets: encryption and password managers

Source: <https://www.chezmoi.io/user-guide/encryption/>, <https://www.chezmoi.io/reference/templates/> (password manager functions).

Two approaches — pick per secret:
- **Password manager function in a template**: secret never touches the repo. Best for tokens, API keys.
- **Encrypted file** (`encrypted_` + age/gpg): whole file stored encrypted in the repo. Best for SSH keys,
  files with many secrets, or machines without a password manager.

Safety net: `[add] secrets = "error"` makes `chezmoi add` refuse files that look like they contain secrets.
`--skip-secrets` skips templates that need secrets (e.g. in CI).

## age (recommended)

```bash
chezmoi age-keygen --output ~/.config/chezmoi/key.txt   # prints the public key (age1…)
```

```toml
encryption = "age"          # top level, before sections
[age]
    identity  = "~/.config/chezmoi/key.txt"
    recipient = "age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p"
    # identities = [...]; recipients = [...]; recipientsFile = "..."
    # passphrase = true     # prompt for a passphrase instead of a key
    # symmetric = true      # use identity for symmetric encryption
```

```bash
chezmoi add --encrypt ~/.ssh/id_ed25519   # → private_dot_ssh/encrypted_private_id_ed25519.age
chezmoi edit ~/.ssh/id_ed25519            # transparently decrypts/re-encrypts
chezmoi edit-encrypted <source-file>
chezmoi decrypt < file.age                # / chezmoi encrypt
chezmoi re-add --re-encrypt               # after changing recipients
```

Built-in age (used when the `age` binary is missing, or `--use-builtin-age`) does **not** support
passphrases, symmetric mode, or SSH keys.

### Bootstrapping the age key on a new machine

Store the key itself passphrase-encrypted in the repo and decrypt it once:

```bash
chezmoi age-keygen | chezmoi age encrypt --passphrase > key.txt.age   # in source root
```

```
# .chezmoiignore
key.txt.age
```

```sh
# .chezmoiscripts/run_onchange_before_00-decrypt-age-key.sh.tmpl
#!/bin/sh
if [ ! -f "${HOME}/.config/chezmoi/key.txt" ]; then
    mkdir -p "${HOME}/.config/chezmoi"
    chezmoi age decrypt --output "${HOME}/.config/chezmoi/key.txt" --passphrase "{{ .chezmoi.sourceDir }}/key.txt.age"
    chmod 600 "${HOME}/.config/chezmoi/key.txt"
fi
```

## gpg

```toml
encryption = "gpg"
[gpg]
    recipient = "you@example.com"     # or recipients = [...]; symmetric = true
```
Suffix `.asc`. Requires `gpg` on every machine.

## Password managers

All are template functions; the CLI must be installed and logged in **before** templates render
(use a `read-source-state.pre` hook to install it — see configuration.md). Results are cached per run.

### Bitwarden (`bw`)
```
{{ (bitwarden "item" "github").login.password }}
{{ (bitwarden "item" "github").login.username }}
{{ (bitwardenFields "item" "aws").accessKeyId.value }}       {{/* custom fields */}}
{{ bitwardenAttachment "id_ed25519" "<item-id>" }}
{{ (bitwardenSecrets "<secret-id>").value }}                  {{/* Bitwarden Secrets Manager (bws) */}}
{{ (rbw "github").data.password }}  {{ (rbwFields "aws").token.value }}   {{/* rbw client */}}
```
Config: `[bitwarden] unlock = "auto"` → runs `bw unlock --raw` if `BW_SESSION` isn't set (and `bw lock` at exit).

### 1Password (`op`)
```
{{ onepasswordRead "op://Personal/GitHub/token" }}
{{ (onepassword "GitHub").fields … }}                    {{/* full item JSON */}}
{{ (onepasswordItemFields "GitHub").token.value }}
{{ (onepasswordDetailsFields "GitHub").password.value }}
{{ onepasswordDocument "ssh-config" }}
```
Optional extra arg = vault, then account. `[onepassword] mode = "account"` (default), `"connect"`, or
`"service"` (service accounts; `account` arg not allowed).

### KeePassXC (`keepassxc-cli`)
```toml
[keepassxc]
    database = "~/Passwords.kdbx"
    # mode = "builtin"   # no CLI needed; "open" keeps an interactive session
```
```
{{ (keepassxc "GitHub").Password }}   {{ (keepassxc "GitHub").UserName }}
{{ keepassxcAttribute "GitHub" "token" }}
{{ keepassxcAttachment "SSH" "id_ed25519" }}
```
Database password is asked once and kept in memory for the run.

### pass / gopass
```
{{ pass "github/token" }}                {{ (passFields "github").user }}
{{ gopass "github/token" }}
```

### Others
LastPass (`lastpass`, `lastpassRaw`), Dashlane, Doppler, Keeper, Proton Pass, HashiCorp Vault (`vault`),
AWS Secrets Manager (`awsSecretsManager`), Azure Key Vault, ejson, Passhole, OS keyring
(`keyring "service" "user"`, set with `chezmoi secret keyring set`).

### Generic command
```toml
[secret]
    command = "my-secret-tool"
    args = ["--format", "json"]
```
```
{{ secret "get" "github-token" }}          {{/* stdout, trimmed */}}
{{ (secretJSON "get" "aws").accessKey }}
```

## Patterns

Secret only on machines that have the manager:
```
{{ if lookPath "op" -}}
export GITHUB_TOKEN={{ onepasswordRead "op://Personal/GitHub/token" | quote }}
{{ end -}}
```

Keep secret-bearing files private: `private_dot_netrc.tmpl`, and check `chezmoi cat ~/.netrc`
renders correctly before `apply`. Never commit rendered output (`chezmoi archive`, `dump`) to a public repo.
