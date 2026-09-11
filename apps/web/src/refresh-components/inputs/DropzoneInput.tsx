import type { InputHTMLAttributes } from "react";

/**
 * DropzoneInput
 *
 * The hidden file input a react-dropzone container needs. `getInputProps()`
 * has to be spread onto a real `<input type="file">` — the browser file picker
 * is what it opens — so the primitive lives here once, in the design system,
 * instead of being written out at every drop target.
 *
 * @example
 * ```tsx
 * const { getRootProps, getInputProps } = useDropzone({ onDrop });
 *
 * <div {...getRootProps()}>
 *   <DropzoneInput {...getInputProps()} />
 *   <Text as="p">Drop a file here</Text>
 * </div>
 * ```
 */
export default function DropzoneInput(
  props: InputHTMLAttributes<HTMLInputElement>
) {
  return <input {...props} />;
}
