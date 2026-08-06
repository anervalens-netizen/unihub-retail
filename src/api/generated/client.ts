import { client } from '../client';
import {
  RETAIL_OPERATION_ROUTES,
  type RetailOperationId,
  type RetailOperationResponses,
} from './contracts';

type SuccessResponse<Id extends RetailOperationId> =
  RetailOperationResponses[Id] extends { '200': infer Response } ? Response :
  RetailOperationResponses[Id] extends { '201': infer Response } ? Response :
  RetailOperationResponses[Id] extends { '202': infer Response } ? Response :
  RetailOperationResponses[Id] extends { '204': infer Response } ? Response :
  never;

export async function generatedGet<Id extends RetailOperationId>(
  operationId: Id,
  params?: object,
  signal?: AbortSignal,
): Promise<SuccessResponse<Id>> {
  const route = RETAIL_OPERATION_ROUTES[operationId];
  if (route.method !== 'get') {
    throw new Error(`Operation ${operationId} is not a GET route`);
  }
  const { data } = await client.get<SuccessResponse<Id>>(route.path, { params, signal });
  return data;
}

export async function generatedPost<Id extends RetailOperationId>(
  operationId: Id,
  body: unknown,
  params?: object,
  signal?: AbortSignal,
): Promise<SuccessResponse<Id>> {
  const route = RETAIL_OPERATION_ROUTES[operationId];
  if (route.method !== 'post') {
    throw new Error(`Operation ${operationId} is not a POST route`);
  }
  const { data } = await client.post<SuccessResponse<Id>>(route.path, body, { params, signal });
  return data;
}
