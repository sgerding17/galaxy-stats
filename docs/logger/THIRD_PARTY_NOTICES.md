# Third-party components

## vosk-browser 0.0.8

The offline grammar recognizer uses the `vosk-browser` WebAssembly runtime by
Ciaran O'Reilly and contributors.

- Source: <https://github.com/ccoreilly/vosk-browser>
- Package: <https://www.npmjs.com/package/vosk-browser/v/0.0.8>
- License: Apache License 2.0; see `vendor/LICENSE-vosk-browser.txt`

## Vosk small US English model 0.15

The recognizer model is `vosk-model-small-en-us-0.15`, copyright 2020 Alpha
Cephei Inc.

- Source: <https://alphacephei.com/vosk/models>
- License: Apache License 2.0
- Original archive SHA-256: `30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498`

The original ZIP was repackaged as a gzip-compressed tar archive, with its
top-level directory renamed to `model`, as required by `vosk-browser`.
