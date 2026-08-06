# cellforge-bundle

`cellforge_bundle` compiles an already-authored cell project into a deterministic deployment plan
and canonical manifest. It performs no binary/container build, publication, installation,
activation, runtime control, or safety function.

The package depends on the pure `cellforge_domain` contracts. The domain package does not import
this application layer. Expected invalid inputs are returned as stable findings in a
`CompilationReport`.

The bundle ID is SHA-256 over canonical UTF-8 JSON for every manifest field except the
self-referential `bundle_id`. The manifest file inventory freezes the exact source content hashes.
Production compilation requires approved recipes and production-qualified hardware adapters, then
fails closed at the explicit evidence-policy placeholder until a real evidence verifier is added.
