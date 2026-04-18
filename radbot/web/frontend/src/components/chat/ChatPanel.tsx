import ChatHeader from "./ChatHeader";
import SessionSubheader from "./SessionSubheader";
import MessageList from "./MessageList";
import ChatInput from "./ChatInput";
import StatsFooter from "./StatsFooter";

export default function ChatPanel() {
  return (
    <div className="flex flex-col h-full bg-bg-primary relative">
      <ChatHeader />
      <SessionSubheader />
      <MessageList />
      <ChatInput />
      <StatsFooter />
    </div>
  );
}
