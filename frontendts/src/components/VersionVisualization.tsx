'use client';

import {
  Brain,
  Brush,
  ChevronDown,
  ChevronUp,
  CloudDownload,
  Edit3,
  MapPlus,
  MessageCirclePlus,
  Minus,
  TextSearch,
  Upload,
  User,
  Wrench,
  ZoomIn,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import SyntaxHighlighter from 'react-syntax-highlighter';
import { dark } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import remarkGfm from 'remark-gfm';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { QgisIcon } from '@/lib/qgis';
import {
  Conversation,
  EphemeralAction,
  MapNode,
  MapTreeResponse,
  SanitizedMessage,
  SanitizedToolCall,
  SanitizedToolResponse,
} from '@/lib/types';
import { formatShortRelativeTime } from '../lib/utils';

function iconForToolCall(toolCall: SanitizedToolCall) {
  switch (toolCall.icon) {
    case 'text-search':
      return <TextSearch className="w-4 h-4" />;
    case 'brush':
      return <Brush className="w-4 h-4" />;
    case 'wrench':
      return <Wrench className="w-4 h-4" />;
    case 'map-plus':
      return <MapPlus className="w-4 h-4" />;
    case 'cloud-download':
      return <CloudDownload className="w-4 h-4" />;
    case 'zoom-in':
      return <ZoomIn className="w-4 h-4" />;
    case 'qgis':
      return <QgisIcon className="w-4 h-4" />;
  }
}

function isExpandable(toolCall: SanitizedToolCall) {
  return toolCall.code || toolCall.table;
}

function MessageItem({
  message,
  msgIndex,
  expandedToolCalls,
  setExpandedToolCalls,
  toolResponses,
}: {
  message: SanitizedMessage;
  msgIndex: number;
  expandedToolCalls: string[];
  setExpandedToolCalls: (toolCalls: string[]) => void;
  toolResponses: SanitizedToolResponse[];
}) {
  // Create lookup table from toolCall.id to toolStatus
  const toolStatusLookup =
    message.tool_calls?.reduce(
      (acc, toolCall) => {
        const toolResponse = toolResponses.find((response) => response.id === toolCall.id);
        acc[toolCall.id] = toolResponse?.status || 'pending';
        return acc;
      },
      {} as Record<string, string>,
    ) || {};

  const toolColorLookup: Record<string, string> = {
    success: 'text-muted-foreground',
    error: 'text-red-400',
  };

  const toolHoverColorLookup: Record<string, string> = {
    success: 'hover:text-gray-100',
    error: 'hover:text-red-300',
  };

  return (
    <>
      <div
        key={msgIndex}
        className={`text-halfway-sm-xs ${message.role === 'user' ? 'rounded bg-gray-700 text-right py-0.5 px-2 max-w-3/4 ml-auto' : ''}`}
      >
        <div className="flex-1 min-w-0 text-white">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        </div>
      </div>
      {message.tool_calls && message.tool_calls.length > 0 && (
        <div>
          {message.tool_calls.map((toolCall) => (
            <div key={toolCall.id} className="space-y-1">
              <div
                className={`flex justify-start gap-2 ${toolColorLookup[toolStatusLookup[toolCall.id]]} ${isExpandable(toolCall) ? `cursor-pointer ${toolHoverColorLookup[toolStatusLookup[toolCall.id]]}` : ''}`}
                onClick={() => {
                  if (isExpandable(toolCall)) {
                    const isExpanded = expandedToolCalls.includes(toolCall.id);
                    if (isExpanded) {
                      setExpandedToolCalls(expandedToolCalls.filter((id) => id !== toolCall.id));
                    } else {
                      setExpandedToolCalls([...expandedToolCalls, toolCall.id]);
                    }
                  }
                }}
                title={toolStatusLookup[toolCall.id] === 'error' ? 'Tool call failed' : 'Tool call succeeded'}
              >
                <div>{iconForToolCall(toolCall)}</div>
                <div>{toolCall.tagline}</div>
                {isExpandable(toolCall) && (
                  <div>
                    {expandedToolCalls.includes(toolCall.id) ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </div>
                )}
              </div>
              {toolCall.code && expandedToolCalls.includes(toolCall.id) && (
                <div>
                  <pre className="text-left bg-gray-800 rounded text-xs overflow-x-scroll">
                    <SyntaxHighlighter
                      language={toolCall.code.language}
                      style={dark}
                      className="rounded border-gray-500 border bg-slate-900!"
                    >
                      {toolCall.code.code}
                    </SyntaxHighlighter>
                  </pre>
                </div>
              )}
              {toolCall.table && expandedToolCalls.includes(toolCall.id) && (
                <div className="text-left bg-slate-900 border-gray-500 border rounded text-xs overflow-x-scroll">
                  <table className="w-full border-collapse">
                    <tbody>
                      {Object.entries(toolCall.table).map(([key, value], index, array) => (
                        <tr key={key} className={index < array.length - 1 ? 'border-b border-gray-600' : ''}>
                          <td className="px-2 py-1 font-medium text-gray-300">{key}</td>
                          <td className="px-2 py-1 text-white">{value}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}

interface VersionVisualizationProps {
  mapTree: MapTreeResponse | null;
  conversationId: number | null;
  currentMapId: string | null;
  conversations: Conversation[];
  setConversationId: (conversationId: number | null) => void;
  activeActions: EphemeralAction[];
  conversationsEnabled?: boolean;
}

export default function VersionVisualization({
  mapTree,
  conversationId,
  currentMapId,
  conversations,
  setConversationId,
  activeActions,
  conversationsEnabled = true,
}: VersionVisualizationProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [expandedToolCalls, setExpandedToolCalls] = useState<string[]>([]);
  const [expandedEditGroups, setExpandedEditGroups] = useState<string[]>([]);

  // Helper function to get messages for a specific map_id
  const getMessagesForMap = useCallback(
    (mapId: string) => {
      const node = mapTree?.tree.find((n) => n.map_id === mapId);
      if (!node) return [];
      return node.messages
        .filter((msg) => msg.role !== 'system')
        .sort((a, b) => {
          // Sort by created_at timestamp if available, otherwise maintain original order
          if (a.created_at && b.created_at) {
            return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
          }
          return 0;
        });
    },
    [mapTree],
  );

  const getEditIcon = useCallback((node: MapNode) => {
    if (!node.diff_from_previous) return null;

    const { added_layers, removed_layers } = node.diff_from_previous;
    if (added_layers.length > 0 && removed_layers.length > 0) {
      return <Edit3 className="w-4 h-4" />;
    }
    if (added_layers.length > 0) {
      return <Upload className="w-3 h-3 inline-block mb-0.5" />;
    }
    if (removed_layers.length > 0) {
      return <Minus className="w-4 h-4" />;
    }
    return <Edit3 className="w-4 h-4" />;
  }, []);

  const getEditDescription = useCallback((node: MapNode) => {
    if (!node.diff_from_previous) return 'Created map';

    const { added_layers, removed_layers } = node.diff_from_previous;
    const parts = [];

    if (added_layers.length > 0) {
      parts.push(`${added_layers.map((layer) => layer.name).join(', ')}`);
    }
    if (removed_layers.length > 0) {
      parts.push(`${removed_layers.map((layer) => layer.name).join(', ')}`);
    }

    return parts.length > 0 ? parts.join(', ') : 'Layer changes';
  }, []);

  const getNodePresentation = useCallback(
    (node: MapNode) => {
      const editor: string = node.fork_reason == 'ai_edit' ? 'Kue' : 'You';
      const icon: React.ReactNode =
        node.fork_reason == 'ai_edit' ? <Brain className="w-4 h-4 text-black" /> : <User className="w-4 h-4 text-black" />;
      const color: string = node.map_id === currentMapId ? 'bg-green-400' : 'bg-gray-300';
      const textColor: string = node.map_id === currentMapId ? 'text-green-400' : 'text-gray-300';
      return { editor, icon, color, textColor };
    },
    [currentMapId],
  );

  // Do not early-return here to avoid conditional hooks; below render paths handle null mapTree gracefully

  // Build grouped display items where runs of map nodes with no messages are collapsed
  const MIN_GROUP_SIZE = 3; // collapse only when there are 3 or more consecutive edits with no messages

  type DisplayItem = { type: 'node'; node: MapNode } | { type: 'group'; id: string; nodes: MapNode[] };

  const displayItems: DisplayItem[] = useMemo(() => {
    if (!mapTree) return [];
    const items: DisplayItem[] = [];
    const nodes = mapTree.tree;

    let i = 0;
    while (i < nodes.length) {
      const node = nodes[i];
      const messages = getMessagesForMap(node.map_id);
      if (messages.length === 0) {
        // Start of a potential group
        let j = i;
        while (j < nodes.length) {
          const hasMsgs = getMessagesForMap(nodes[j].map_id).length > 0;
          if (hasMsgs) break;
          j++;
        }
        const runLength = j - i;
        if (runLength >= MIN_GROUP_SIZE) {
          const groupNodes = nodes.slice(i, j);
          const groupId = `conv-${conversationId ?? 'new'}-group-${groupNodes[0].map_id}-${groupNodes[groupNodes.length - 1].map_id}`;
          items.push({ type: 'group', id: groupId, nodes: groupNodes });
          i = j;
          continue;
        }
        // Not enough to form group, push nodes individually
        items.push({ type: 'node', node });
        i++;
      } else {
        items.push({ type: 'node', node });
        i++;
      }
    }
    return items;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapTree, getMessagesForMap, conversationId]);

  // Auto-expand any group that contains the current map id so it remains visible
  useEffect(() => {
    if (!currentMapId) return;
    const containing = displayItems.find((it) => it.type === 'group' && it.nodes.some((n) => n.map_id === currentMapId)) as
      | Extract<DisplayItem, { type: 'group' }>
      | undefined;
    if (containing) {
      setExpandedEditGroups((prev) => (prev.includes(containing.id) ? prev : [...prev, containing.id]));
    }
  }, [currentMapId, displayItems]);

  const toggleGroup = (groupId: string) => {
    setExpandedEditGroups((prev) => (prev.includes(groupId) ? prev.filter((id) => id !== groupId) : [...prev, groupId]));
  };

  // Renderer for a single map node (edit + its messages)
  const renderMapNode = (node: MapNode) => {
    return (
      <div key={node.map_id} className="relative">
        {/* Map edit node */}
        <div className="flex items-center gap-4">
          {/* Left side - Edit indicator */}
          <div className="flex-4 flex justify-between text-halfway-sm-xs">
            <div className="flex items-baseline">
              <span className="text-gray-400 text-halfway-sm-xs" title={new Date(node.created_on).toLocaleString()}>
                <span className="text-gray-200">{node.fork_reason == 'ai_edit' ? 'Kue, ' : 'You, '}</span>
                {formatShortRelativeTime(node.created_on)}
              </span>
            </div>
            <div className="flex items-baseline">
              <div className={`${getNodePresentation(node).textColor}`}>{getEditIcon(node)}</div>
              <div className="text-halfway-sm-xs ml-1">
                <div className="dark:text-gray-200 text-ellipsis overflow-hidden">{getEditDescription(node)}</div>
              </div>
            </div>
          </div>

          {/* Center - Timeline dot */}
          <div className="relative z-10 flex flex-col items-center">
            <div className={`flex items-center justify-center w-6 h-6 rounded-full ${getNodePresentation(node).color}`}>
              {getNodePresentation(node).icon}
            </div>
          </div>
        </div>

        {/* Messages associated with this map_id */}
        <div className="flex">
          {/* Left side - Messages */}
          <div className="flex flex-col space-y-1 py-2 flex-4">
            {(() => {
              const messages = getMessagesForMap(node.map_id);
              const toolResponses = messages.filter((msg) => msg.role === 'tool' && msg.tool_response).map((msg) => msg.tool_response!);

              return messages.map((msg, msgIndex) => (
                <MessageItem
                  key={`message-${node.map_id}-${msgIndex}`}
                  message={msg}
                  msgIndex={msgIndex}
                  expandedToolCalls={expandedToolCalls}
                  setExpandedToolCalls={setExpandedToolCalls}
                  toolResponses={toolResponses}
                />
              ));
            })()}
          </div>

          {/* Center - connecting line space */}
          <div className="w-6 flex justify-center">
            <div className={`relative w-0.25 h-full min-h-4 ${getNodePresentation(node).color}`}></div>
          </div>
        </div>
      </div>
    );
  };

  return conversationsEnabled ? (
    <div className="z-30 max-h-screen h-full w-96 bg-white dark:bg-gray-800 shadow-md flex flex-col text-halfway-sm-xs">
      <div className="flex-1 overflow-auto p-2">
        <div className="mb-4 bg-gray-700 rounded-md">
          <div className="p-2 flex items-center justify-between">
            <div
              className="flex items-center gap-2 cursor-pointer hover:bg-gray-600 p-1 rounded w-fit group"
              onClick={() => setIsExpanded(!isExpanded)}
            >
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex items-center gap-2">
                    <h4 className="text-md font-semibold text-gray-100">Previous chats</h4>
                    <div className="text-gray-500 group-hover:text-gray-300">
                      {isExpanded ? <ChevronUp className="w-4.5 h-4.5" /> : <ChevronDown className="w-4.5 h-4.5" />}
                    </div>
                  </div>
                </TooltipTrigger>
                <TooltipContent>
                  <p>
                    {isExpanded ? 'Hide' : 'Show'} {conversations.length} previous chat{conversations.length > 1 ? 's' : ''}
                  </p>
                </TooltipContent>
              </Tooltip>
            </div>
            <div
              className={`p-1 ${conversationId === null ? 'text-gray-600 cursor-not-allowed' : 'text-gray-500 hover:text-gray-300 cursor-pointer'}`}
              onClick={conversationId === null ? undefined : () => setConversationId(null)}
            >
              <Tooltip>
                <TooltipTrigger asChild>
                  <MessageCirclePlus className="w-4.5 h-4.5" />
                </TooltipTrigger>
                <TooltipContent>
                  <p>{conversationId === null ? 'You are in a new chat' : 'Start a new chat'}</p>
                </TooltipContent>
              </Tooltip>
            </div>
          </div>
          {isExpanded && (
            <div className="space-y-1 max-h-32 overflow-y-auto pb-2">
              {conversations.map((conversation) => (
                <div
                  key={conversation.id}
                  className={`text-halfway-sm-xs py-1 px-2 cursor-pointer group ${
                    conversation.id === conversationId
                      ? 'bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200'
                      : 'hover:bg-gray-600 text-gray-300 hover:text-gray-100'
                  }`}
                  onClick={() => setConversationId(conversation.id)}
                >
                  <div className="flex items-center justify-between min-w-0">
                    <span className="font-medium shrink text-ellipsis overflow-hidden whitespace-nowrap min-w-0">{conversation.title}</span>
                    <div className="shrink-0 text-gray-400">
                      <span className="group-hover:hidden">{formatShortRelativeTime(conversation.updated_at)}</span>
                      <span className="hidden group-hover:inline">{conversation.message_count} messages</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="relative">
          {displayItems.map((item) => {
            if (item.type === 'node') {
              return renderMapNode(item.node);
            }
            const { id, nodes } = item;
            const isOpen = expandedEditGroups.includes(id);
            const count = nodes.length;
            return (
              <div key={id} className="relative">
                {/* Collapsed/Expanded group header */}
                <div className="flex items-center gap-4">
                  {/* Left side - Group indicator */}
                  <div className="flex-4 flex justify-between text-halfway-sm-xs">
                    <div className="flex items-center gap-2">
                      <button
                        className={`flex items-center gap-2 text-gray-300 hover:text-gray-100 cursor-pointer`}
                        onClick={() => toggleGroup(id)}
                        title={isOpen ? 'Collapse edits' : 'Expand edits'}
                      >
                        {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        <Edit3 className="w-4 h-4" />
                        <span className="whitespace-nowrap">
                          {count} {isOpen ? 'visible' : 'hidden'} edits
                        </span>
                      </button>
                    </div>
                    <div />
                  </div>

                  {/* Center - Group timeline dot */}
                  <div className="relative z-10 flex flex-col items-center">
                    <div className={`flex items-center justify-center w-6 h-6 rounded-full bg-gray-300`}>
                      <Edit3 className="w-4 h-4 text-black" />
                    </div>
                  </div>
                </div>

                {/* Center - connecting line space under header */}
                <div className="flex">
                  <div className="flex flex-col space-y-1 py-2 flex-4"></div>
                  <div className="w-6 flex justify-center">
                    <div className={`relative w-0.25 h-full min-h-4 bg-gray-300`}></div>
                  </div>
                </div>

                {/* Expanded content */}
                {isOpen && nodes.map((n) => renderMapNode(n))}
              </div>
            );
          })}

          {activeActions.length > 0 && (
            <div className="relative">
              {/* Map edit node */}
              <div className="flex items-center gap-4">
                <div className="flex-4 flex justify-end items-center">
                  {activeActions.length > 0 ? (
                    <div className="text-halfway-sm-xs text-gray-400 whitespace-nowrap">
                      <span className="text-gray-300 text-right">Kue is thinking...</span>
                    </div>
                  ) : null}
                </div>

                {/* Center - Timeline dot */}
                <div className="relative z-10 flex flex-col items-center">
                  <div className={`flex items-center justify-center w-6 h-6 rounded-full bg-green-400`}>
                    <Brain className="w-4 h-4 text-black animate-spin" />
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* New Chat Button */}
        <div className="mt-4 flex justify-center">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                onClick={() => setConversationId(null)}
                variant="default"
                // disabled={conversationId === null}
                className={conversationId === null ? 'cursor-not-allowed text-sm' : 'cursor-pointer'}
              >
                {conversationId === null ? 'Type message and hit enter to chat' : 'New Chat'}
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              <p>{conversationId === null ? 'You are already in a new chat' : 'Start a new chat'}</p>
            </TooltipContent>
          </Tooltip>
        </div>
      </div>
    </div>
  ) : null;
}
