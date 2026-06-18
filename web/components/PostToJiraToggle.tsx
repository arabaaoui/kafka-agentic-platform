"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { postToJira } from "@/lib/api";

interface Props {
  missionId: string;
  jiraTicketId?: string | null;
  alreadyPosted: boolean;
}

export function PostToJiraToggle({ missionId, jiraTicketId, alreadyPosted }: Props) {
  const [confirming, setConfirming] = useState(false);
  const qc = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => postToJira(missionId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["mission", missionId] });
      setConfirming(false);
    },
  });

  if (alreadyPosted) {
    return (
      <div className="flex items-center gap-2 text-xs text-green-400">
        <span className="w-2 h-2 rounded-full bg-green-500 inline-block" />
        Posted to Jira
        {jiraTicketId && (
          <span className="text-gray-500">({jiraTicketId})</span>
        )}
      </div>
    );
  }

  if (confirming) {
    return (
      <div className="flex flex-col gap-2 p-3 bg-gray-800 border border-amber-700 rounded text-xs">
        <p className="text-amber-300 font-medium">
          Post the audit summary to Jira ticket
          {jiraTicketId ? ` ${jiraTicketId}` : ""}?
        </p>
        <p className="text-gray-400 text-xs">
          This will add a comment with ranked hypotheses. This action cannot be undone.
        </p>
        <div className="flex gap-2 mt-1">
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            className="px-3 py-1 bg-amber-600 hover:bg-amber-500 text-white rounded text-xs disabled:opacity-50"
          >
            {mutation.isPending ? "Posting…" : "Confirm post"}
          </button>
          <button
            onClick={() => setConfirming(false)}
            className="px-3 py-1 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-xs"
          >
            Cancel
          </button>
        </div>
        {mutation.isError && (
          <p className="text-red-400 mt-1">
            {(mutation.error as Error).message}
            <button
              onClick={() => mutation.mutate()}
              className="ml-2 underline"
            >
              Retry
            </button>
          </p>
        )}
      </div>
    );
  }

  return (
    <button
      onClick={() => setConfirming(true)}
      className="flex items-center gap-2 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 border border-gray-600 hover:border-amber-600 rounded text-xs text-gray-300 hover:text-amber-300 transition-colors"
    >
      <span className="w-2 h-2 rounded-full bg-gray-600 inline-block" />
      Post to Jira
    </button>
  );
}
