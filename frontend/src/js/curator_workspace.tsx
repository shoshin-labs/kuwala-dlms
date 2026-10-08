import React from "react";
import { MuiPickersUtilsProvider } from "@material-ui/pickers";
import DateFnsUtils from "@date-io/date-fns";
import MainScreen from "./main";
import GlobalState from "./context/global_state";

export default function CuratorWorkspace() {
  return (
    <MuiPickersUtilsProvider utils={DateFnsUtils}>
      <GlobalState render={MainScreen} />
    </MuiPickersUtilsProvider>
  );
}
