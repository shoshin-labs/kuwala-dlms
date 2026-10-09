import managerEnglish from "./locales/manager.en.json";
import { get, isString } from 'lodash'
import { produce } from 'immer'
import XLSX from 'xlsx'
import { SerializedMetadata, field_info } from './types'


// Gets a SerlializedMetadata given an array of SerializedMetadata and an id to look for
// If none found, return null
// If multiple found, return the first one found
export const get_metadata = (metadata: SerializedMetadata[], id: number): SerializedMetadata | null => {
    const filtered = metadata.filter(val => val.id === id)
    return get(filtered, 0, null)
}


// Custom implementation of setState, just abstracts away boilerplate so we can save lines when using immer functions
// Also allows us to use promises instead of a callback
// Also gives us a way to update complex state by mutating it instead of making a new object every time
// Usage in constructor:
//   this.update_state = update_state.bind(this)
//
// Make sure the type of this.update_state is
//   update_func: (draft: COMPONENT_STATE_TYPE) => void) => Promise<void>
//
// Usage example:
// this.update_state(draft => {
//   draft.create_meta.type_name = "string value"
//   draft.create_meta.is_open = true
// })
//
// This would update this.state.create_meta.type_name to "string value" and this.state.create_meta.is_open to true
export async function update_state<T>(this: any, update_func: (draft: T) => void): Promise<void> {
    return new Promise((resolve, reject)=> {
        try {
            this.setState((prevState: T) => {
                return produce(prevState, update_func)
            }, resolve)
        } catch(err) {
            reject(err)
        }
    })
}


// Given a standard api error response this will look for a string in the object and if it cant find it
// will return a default error message.
// This was written to be used to find an error string that could be passed to an error toast when
// a call to axios failed.
//
// Usage example: 
// this.props.show_toast_message(get_string_from_error(
//   reason.response.data.error, "Error while adding content"
// ))
// 
// where reason is the object passed as an argument to the catch function when the piped axios call fails,
// not the actual error object from the database 
export const get_string_from_error = (err_obj: any, default_err: string): string => {
    try {
        //This returns the error object if its a string or looks for an error string as the value
        //to the first object key's first member (in case of validation error)
        //Javascript will choose which key is first randomly
        //The syntax looks weird but this just creates an anonymous function and immediately calls it
        //so we can define variables for use in inline if expressions
        return isString(err_obj) ? err_obj : (() => {
            const first_msg = err_obj[Object.keys(err_obj)[0]][0]
            return isString(first_msg) ? first_msg : default_err
        })()
    } catch {
        return default_err
    }
}

// Creates and returns a field_info object with no validation error from a default value
export function get_field_info_default<T>(value: T): field_info<T> {
    return {
        value,
        reason: ""
    }
}
//converts excel sheet data to JSON Format
export function read_excel_file(fileUploaded: File | null | undefined) {
    return new Promise( (getData, reject) => {
      if (!fileUploaded) {reject(new Error(managerEnglish.strings.bulk_sheet_required)); return;}
      const readFile = new FileReader();
      readFile.onerror = () => reject(new Error(managerEnglish.strings.bulk_read_error));
      readFile.onabort = () => reject(new Error(managerEnglish.strings.bulk_read_cancelled));
      readFile.onload = () => {
        try {
        const storeData: any = readFile.result;
        const data = new Uint8Array(storeData);
        const arr = new Array();
        for (let i = 0; i !== data.length; ++i) { arr[i] = String.fromCharCode(data[i]); }
        const bstr = arr.join('');
        const workbook = XLSX.read(bstr, { type: 'binary' });
        const firstSheetName = workbook.SheetNames[0];
        const jsonData = XLSX.utils.sheet_to_json(workbook.Sheets[firstSheetName], { raw: true, defval: ''});
        getData(JSON.stringify(jsonData));
        } catch (error) {reject(error);}
      };
      readFile.readAsArrayBuffer(fileUploaded!);
    });
  }
