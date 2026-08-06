import type { RetailDecimal } from './contracts';
import { RETAIL_DECIMAL_KEYS } from './contracts';

export type DecodeRetail<T> =
  T extends RetailDecimal ? number :
  T extends Blob ? T :
  T extends readonly unknown[] ?
    number extends T['length'] ? Array<DecodeRetail<T[number]>> : { [Key in keyof T]: DecodeRetail<T[Key]> } :
  T extends object ? { [Key in keyof T]: DecodeRetail<T[Key]> } :
  T;

function decodeValue(value: unknown, key?: string): unknown {
  if (value === null || value === undefined) return value;
  if (typeof Blob !== 'undefined' && value instanceof Blob) return value;
  if (key && RETAIL_DECIMAL_KEYS.has(key) && typeof value === 'string') {
    const numeric = Number(value);
    // `value` is also used by string-valued filter/evaluation options. Keep
    // those labels intact while still decoding numeric financial values.
    if (!Number.isFinite(numeric)) {
      if (key === 'value') return value;
      throw new Error(`Invalid Retail Decimal for ${key}`);
    }
    return numeric;
  }
  if (Array.isArray(value)) return value.map((item) => decodeValue(item));
  if (typeof value !== 'object') return value;
  return Object.fromEntries(
    Object.entries(value).map(([childKey, childValue]) => [childKey, decodeValue(childValue, childKey)]),
  );
}

export function decodeRetail<T>(value: unknown): DecodeRetail<T> {
  return decodeValue(value) as DecodeRetail<T>;
}
