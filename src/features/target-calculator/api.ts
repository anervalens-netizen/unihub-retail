/** Target Calculator API boundary; keeps page and hooks independent of API layout. */
export {
  calculateTargetScenario,
  downloadTargetScenario,
  fetchTargetCalculatorContext,
  fetchTargetScenario,
  fetchTargetScenarios,
  fetchTargetStoreDetail,
  finalizeTargetScenario,
  saveTargetFinalValues,
} from '../../api/targetCalculator';

export type {
  TargetCalculatorContext,
  TargetProfitability,
  TargetScenario,
  TargetScenarioRow,
  TargetStoreDetail,
} from '../../api/targetCalculator';
