import React from 'react';
import ReactDOM from 'react-dom';

import OasisApp, { AppBoundary } from './oasis_app';
import { setAutoFreeze, enableMapSet } from 'immer';

setAutoFreeze(false)
enableMapSet()

/*
* Load main screen
*/
ReactDOM.render(
    (<AppBoundary><OasisApp /></AppBoundary>)
    ,
    document.getElementById('container')
);
