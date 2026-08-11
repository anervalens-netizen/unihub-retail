/* HANDWRITTEN RETAIL BOUNDARY: runtime decoding for generated contracts. */
import type { RetailDecimal, RetailOperationId } from "./contracts";
import {
  RETAIL_DATE_PATHS,
  RETAIL_DATETIME_PATHS,
  RETAIL_DECIMAL_PATHS,
} from "./contracts";
import {
  RETAIL_COMPONENT_SCHEMAS,
  RETAIL_RESPONSE_SCHEMAS,
  RETAIL_RUNTIME_VALIDATED_OPERATIONS,
  type RetailRuntimeSchema,
} from "./runtime-schemas";

type RuntimeSchema = RetailRuntimeSchema;

export class RetailContractError extends Error {
  readonly operationId: RetailOperationId;
  readonly responsePath: string;

  constructor(operationId: RetailOperationId, responsePath: string, reason: string) {
    super(`Invalid Retail response for ${operationId} at ${responsePath}: ${reason}`);
    this.name = "RetailContractError";
    this.operationId = operationId;
    this.responsePath = responsePath;
  }
}

function schemaRecord(value: unknown): RuntimeSchema | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as RuntimeSchema)
    : null;
}

function schemaBranches(schema: RuntimeSchema, key: "anyOf" | "oneOf" | "allOf"): RuntimeSchema[] {
  const value = schema[key];
  return Array.isArray(value)
    ? value.map(schemaRecord).filter((branch): branch is RuntimeSchema => branch !== null)
    : [];
}

function contractFailure(operationId: RetailOperationId, path: string, reason: string): never {
  throw new RetailContractError(operationId, path || "$", reason);
}

export function validateRetailSchema(
  operationId: RetailOperationId,
  schema: RuntimeSchema,
  value: unknown,
  path = "$",
): void {
  const reference = schema.$ref;
  if (typeof reference === "string") {
    const name = reference.split("/").at(-1);
    const target = name
      ? schemaRecord((RETAIL_COMPONENT_SCHEMAS as Record<string, unknown>)[name])
      : null;
    if (!target) contractFailure(operationId, path, `unknown schema reference ${reference}`);
    validateRetailSchema(operationId, target, value, path);
    return;
  }

  const anyOf = schemaBranches(schema, "anyOf");
  if (anyOf.length > 0) {
    for (const branch of anyOf) {
      try {
        validateRetailSchema(operationId, branch, value, path);
        return;
      } catch (error) {
        if (!(error instanceof RetailContractError)) throw error;
      }
    }
    contractFailure(operationId, path, "does not match any allowed schema");
  }
  const oneOf = schemaBranches(schema, "oneOf");
  if (oneOf.length > 0) {
    let matches = 0;
    for (const branch of oneOf) {
      try {
        validateRetailSchema(operationId, branch, value, path);
        matches += 1;
      } catch (error) {
        if (!(error instanceof RetailContractError)) throw error;
      }
    }
    if (matches !== 1) contractFailure(operationId, path, "does not match exactly one schema");
    return;
  }
  for (const branch of schemaBranches(schema, "allOf")) {
    validateRetailSchema(operationId, branch, value, path);
  }

  const allowed = schema.enum;
  if (Array.isArray(allowed) && !allowed.some((candidate) => Object.is(candidate, value))) {
    contractFailure(operationId, path, "value is outside enum");
  }
  if (Object.hasOwn(schema, "const") && !Object.is(schema.const, value)) {
    contractFailure(operationId, path, "value differs from const");
  }

  const expectedType = schema.type;
  const typeMatches = (candidate: unknown): boolean => {
    if (candidate === "null") return value === null;
    if (candidate === "array") return Array.isArray(value);
    if (candidate === "object") return schemaRecord(value) !== null;
    if (candidate === "integer") return typeof value === "number" && Number.isInteger(value);
    if (candidate === "number") return typeof value === "number" && Number.isFinite(value);
    return typeof candidate === "string" && typeof value === candidate;
  };
  if (
    (typeof expectedType === "string" && !typeMatches(expectedType))
    || (Array.isArray(expectedType) && !expectedType.some(typeMatches))
  ) {
    contractFailure(operationId, path, `expected ${String(expectedType)}`);
  }

  if (typeof value === "string") {
    if (typeof schema.minLength === "number" && value.length < schema.minLength)
      contractFailure(operationId, path, "string is too short");
    if (typeof schema.maxLength === "number" && value.length > schema.maxLength)
      contractFailure(operationId, path, "string is too long");
    if (typeof schema.pattern === "string" && !new RegExp(schema.pattern).test(value))
      contractFailure(operationId, path, "string does not match pattern");
  }
  if (typeof value === "number") {
    if (typeof schema.minimum === "number" && value < schema.minimum)
      contractFailure(operationId, path, "number is below minimum");
    if (typeof schema.maximum === "number" && value > schema.maximum)
      contractFailure(operationId, path, "number is above maximum");
  }
  if (Array.isArray(value)) {
    if (typeof schema.minItems === "number" && value.length < schema.minItems)
      contractFailure(operationId, path, "array is too short");
    if (typeof schema.maxItems === "number" && value.length > schema.maxItems)
      contractFailure(operationId, path, "array is too long");
    const items = schemaRecord(schema.items);
    if (items) value.forEach((item, index) => validateRetailSchema(operationId, items, item, `${path}/${index}`));
  }
  const objectValue = schemaRecord(value);
  if (objectValue) {
    const required = Array.isArray(schema.required)
      ? schema.required.filter((name): name is string => typeof name === "string")
      : [];
    for (const name of required) {
      if (!Object.hasOwn(objectValue, name)) contractFailure(operationId, `${path}/${name}`, "required field is missing");
    }
    const properties = schemaRecord(schema.properties) ?? {};
    for (const [name, child] of Object.entries(objectValue)) {
      const childSchema = schemaRecord(properties[name]);
      if (childSchema) validateRetailSchema(operationId, childSchema, child, `${path}/${name}`);
      else if (schema.additionalProperties === false)
        contractFailure(operationId, `${path}/${name}`, "unexpected field");
      else {
        const additionalSchema = schemaRecord(schema.additionalProperties);
        if (additionalSchema) validateRetailSchema(operationId, additionalSchema, child, `${path}/${name}`);
      }
    }
  }
}

export function validateRetailResponse<Id extends RetailOperationId>(
  operationId: Id,
  value: unknown,
): void {
  if (!RETAIL_RUNTIME_VALIDATED_OPERATIONS.has(operationId as never)) return;
  const schema = schemaRecord(
    (RETAIL_RESPONSE_SCHEMAS as Record<RetailOperationId, unknown>)[operationId],
  );
  if (schema) validateRetailSchema(operationId, schema, value);
}

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
  validateRetailResponse(operationId, value);
  return decodeValue(
    value,
    RETAIL_DECIMAL_PATHS[operationId],
    RETAIL_DATE_PATHS[operationId],
    RETAIL_DATETIME_PATHS[operationId],
  ) as DecodeRetail<T>;
}
