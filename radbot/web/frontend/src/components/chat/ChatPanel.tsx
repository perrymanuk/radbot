import ChatHeader from "./ChatHeader";
import MessageList from "./MessageList";
import ChatInput from "./ChatInput";

export default function ChatPanel() {
  return (
    <div className="flex flex-col h-full bg-bg-primary relative">
      <ChatHeader />
      <MessageList />
      <ChatInput />
    </div>
  );
}
