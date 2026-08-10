# PKI Templates

This directory contains non-secret OpenSSL templates for the production PKI foundation. It must not contain generated keys, issued certificates, CSRs, CA databases, serial files, CRLs, or tenant-specific trust bundles.

Use these templates to keep development, validation, and production certificate profiles aligned:

- `templates/root-ca.openssl.cnf`
- `templates/gateway-server-intermediate.openssl.cnf`
- `templates/agent-client-intermediate.openssl.cnf`
- `templates/gateway-server-cert.openssl.cnf`
- `templates/node-agent-client-cert.openssl.cnf`

Production private keys should be generated and stored outside this repository, preferably in offline, HSM, KMS, Vault, or equivalent controlled custody.
