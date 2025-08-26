// Copyright Bunting Labs, Inc. 2025

import type { ChatCompletionMessageParam } from 'openai/resources/chat/completions';

// Define the type for chat completion messages from the database
export interface ChatCompletionMessageRow {
  id: number;
  map_id: string;
  conversation_id: number;
  sender_id: string;
  message_json: ChatCompletionMessageParam;
  created_at: string;
}

// Define the type for error entries
export interface ErrorEntry {
  id: string;
  message: string;
  timestamp: Date;
  shouldOverrideMessages: boolean;
  sourceId?: string;
}

// Add interface for tracking upload progress
export interface UploadingFile {
  id: string;
  file: File;
  progress: number;
  status: 'uploading' | 'completed' | 'error';
  error?: string;
}
