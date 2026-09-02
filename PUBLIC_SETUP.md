# Public setup and privacy

ScheduleBot is a local desktop application. Calendar data and stream-planning data
stay in the user's OS application-data directory. Passwords, API keys, OAuth tokens,
and client secrets are stored through the operating system credential vault.

## Integration setup

- **OBS:** Enable **Tools → WebSocket Server Settings** in OBS. ScheduleBot connects
  to the user's local OBS instance and never exposes the OBS password in its data file.
- **Twitch:** Users enter credentials for a Twitch Developer application and authorize
  through Twitch's Device Code flow. The app requests only broadcast-management and
  clip-creation scopes used by its visible controls.
- **YouTube:** Users select a Google Desktop OAuth JSON file and authorize their own
  channel in the browser. The same connection can create live broadcasts and upload
  regular videos or full VOD files. New, unaudited Google API projects may have their
  uploads restricted to private visibility by Google.
- **Discord:** Users may select a bot-token file or enter a channel webhook. Tokens
  are moved into the OS credential vault.
- **AI VOD:** Users may select local Ollama, which keeps transcript processing local,
  or OpenAI. With OpenAI selected, ScheduleBot sends transcript text to the Responses
  API with response storage disabled; it does not upload the source video.

## Public actions

Starting an OBS stream, updating a Twitch channel, creating a Twitch clip, posting to
Discord and scheduling a YouTube broadcast affect external
accounts. ScheduleBot performs these actions only after the user clicks the matching
button. Users should test with private or unlisted destinations first.

## Distribution checklist

1. Never include the `private/` directory, credential files, or local data files.
2. Publish the privacy and support pages before requesting production OAuth approval.
3. Use platform developer applications owned by the distributor, or clearly require
   users to provide their own developer credentials.
4. Code-sign public Windows builds when possible and publish checksums with releases.
5. Review Twitch, Google, Discord, and OpenAI terms before each public release.
