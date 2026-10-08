const fs = require('fs');
const path = require('path');

// Resolve the generated directory from this file rather than the caller's cwd.
fs.rmSync(path.resolve(__dirname, '../static'), { recursive: true, force: true });
