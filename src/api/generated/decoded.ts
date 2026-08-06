/* HANDWRITTEN RETAIL BOUNDARY: runtime decoding for generated contracts. */
import type { RetailDecimal, RetailOperationId } from "./contracts";
import {
  RETAIL_DATE_PATHS,
  RETAIL_DATETIME_PATHS,
  RETAIL_DECIMAL_PATHS,
} from "./contracts";

export type DecodeRetail<T> = T extends RetailDecimal
  ? number
  : T extends Blob
    ? T
    : T extends FormData
      ? T
      : T extends readonly unknown[]
        ? number extends T["length"]
          ? Array<DecodeRetail<T[number]>>
          : { [Key in keyof T]: DecodeRetail<T[Key]> }
        : T extends object
          ? { [Key in keyof T]: DecodeRetail<T[Key]> }
          : T;

function validateDate(value: unknown, path: string): void {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    throw new Error(`Invalid Retail date for ${path}`);
  }
  const [yearText, monthText, dayText] = value.split("-");
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  if (
    !Number.isInteger(year) ||
    !Number.isInteger(month) ||
    !Number.isInteger(day)
  ) {
    throw new Error(`Invalid Retail date for ${path}`);
  }
  const parsed = new Date(Date.UTC(year, month - 1, day));
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() !== month - 1 ||
    parsed.getUTCDate() !== day
  ) {
    throw new Error(`Invalid Retail date for ${path}`);
  }
}

function validateDateTime(value: unknown, path: string): void {
  if (
    typeof value !== "string" ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(
      value,
    ) ||
    !Number.isFinite(Date.parse(value))
  ) {
    throw new Error(`Invalid Retail date-time for ${path}`);
  }
}

function decodeValue(
  value: unknown,
  decimalPaths: ReadonlySet<string>,
  datePaths: ReadonlySet<string>,
  datetimePaths: ReadonlySet<string>,
  path: string[] = [],
): unknown {
  if (value === null || value === undefined) return value;
  if (typeof Blob !== "undefined" && value instanceof Blob) return value;
  const currentPath = path.join("/");
  if (decimalPaths.has(currentPath)) {
    if (typeof value !== "string")
      throw new Error(`Invalid Retail Decimal for ${currentPath}`);
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      throw new Error(`Invalid Retail Decimal for ${currentPath}`);
    }
    return numeric;
  }
  if (datePaths.has(currentPath)) validateDate(value, currentPath);
  if (datetimePaths.has(currentPath)) validateDateTime(value, currentPath);
  if (Array.isArray(value)) {
    return value.map((item) =>
      decodeValue(item, decimalPaths, datePaths, datetimePaths, [...path, "*"]),
    );
  }
  if (typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value).map(([childKey, childValue]) => [
      childKey,
      decodeValue(childValue, decimalPaths, datePaths, datetimePaths, [
        ...path,
        childKey,
      ]),
    ]),
  );
}

export function decodeRetail<Id extends RetailOperationId, T>(
  operationId: Id,
  value: unknown,
): DecodeRetail<T> {
  return decodeValue(
    value,
    RETAIL_DECIMAL_PATHS[operationId],
    RETAIL_DATE_PATHS[operationId],
    RETAIL_DATETIME_PATHS[operationId],
  ) as DecodeRetail<T>;
}
