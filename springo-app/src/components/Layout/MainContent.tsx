import Header from './Header';
import ChatArea from '@/components/Chat/ChatArea';
import MessageInput from '@/components/Chat/MessageInput';

export default function MainContent() {
  return (
    <div className="main-content">
      <Header />
      <ChatArea />
      <MessageInput />
    </div>
  );
}
