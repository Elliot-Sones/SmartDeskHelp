CREATE TABLE `session_context` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`chat_id` integer NOT NULL,
	`topic` text NOT NULL,
	`embedding` blob NOT NULL,
	`query_count` integer DEFAULT 1,
	`last_used` integer,
	`created_at` integer
);
