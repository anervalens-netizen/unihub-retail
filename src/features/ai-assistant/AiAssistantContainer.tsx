import type { RetailContextUrlState } from '../../lib/insightDeepLink';
import { AiAssistantPanel } from './AiAssistantPanel';
import { useAiAssistant } from './useAiAssistant';

export function AiAssistantContainer({
  canAccess,
  currentContext,
}: {
  canAccess: boolean;
  currentContext: RetailContextUrlState | null;
}) {
  const assistant = useAiAssistant(canAccess);
  return (
    <AiAssistantPanel
      canAccess={canAccess}
      currentContext={currentContext}
      messages={assistant.messages}
      runStatus={assistant.runStatus}
      onSubmit={(submission) => { void assistant.submit(submission); }}
      onStop={() => { void assistant.stop(); }}
      onNewConversation={() => { void assistant.newConversation(); }}
    />
  );
}
