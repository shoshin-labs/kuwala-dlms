import { staticBase } from "./app_paths";

declare let __webpack_public_path__: string;

// This entry runs before index.tsx and its imports, including lazy chunks and
// file-loader assets. One build therefore works at / and at /manage/.
__webpack_public_path__ = staticBase();
