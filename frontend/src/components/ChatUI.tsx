"use client";

import React, { useState, useEffect, useRef } from "react";
import { 
  Plus, 
  Search, 
  MessageSquare, 
  Trash2, 
  Edit2, 
  Settings, 
  ThumbsUp, 
  ThumbsDown, 
  Copy, 
  MoreVertical, 
  RefreshCw, 
  Send,
  Brain,
  Sparkles,
  CheckCircle2,
  FileText,
  X,
  LogOut,
  Folder,
  ChevronRight,
  Home,
  CloudDownload,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { usePathname } from "next/navigation";
import { API_BASE } from "@/lib/api";

function getThreadIdFromPath(pathname: string | null): string {
  const match = pathname?.match(/^\/c\/([^/]+)/);
  return match ? match[1] : "";
}

function updateThreadUrl(id: string) {
  const url = id ? `/c/${id}` : "/";
  window.history.pushState(null, "", url);
}

type Message = {
  id: string;
  role: "user" | "ai";
  content: string;
};

type Thread = {
  id: string;
  title: string;
  created_at: string;
};

type UserProfile = {
  id: string;
  name: string;
  role: string;
};

type DocumentFolder = {
  id: number;
  name: string;
  slug: string;
  path?: string;
  parent_id?: number | null;
  description?: string;
  document_count?: number;
  subfolder_count?: number;
};

type BreadcrumbItem = {
  id: number;
  name: string;
  path?: string;
};

function getFolderMeta(folder: DocumentFolder): string {
  const parts: string[] = [];
  if ((folder.subfolder_count ?? 0) > 0) {
    parts.push(`${folder.subfolder_count} folders`);
  }
  if ((folder.document_count ?? 0) > 0) {
    parts.push(`${folder.document_count} files`);
  }
  return parts.length > 0 ? parts.join(" · ") : "Empty";
}

const HistoryItem = ({ text, active = false, disabled = false, onClick, onDelete }: { text: string, active?: boolean, disabled?: boolean, onClick?: () => void, onDelete?: (e: React.MouseEvent) => void }) => {
  return (
    <div onClick={onClick} className={`group flex items-center justify-between px-4 py-3 rounded-2xl cursor-pointer transition-colors ${active ? 'bg-[#5b61f4]/10' : 'hover:bg-gray-50'}`}>
      <div className="flex items-center gap-3 overflow-hidden">
        <MessageSquare size={18} className={`${active ? 'text-[#5b61f4]' : disabled ? 'text-gray-300' : 'text-gray-400'}`} />
        <span className={`text-sm font-medium truncate ${active ? 'text-[#5b61f4]' : disabled ? 'text-gray-300' : 'text-gray-600'}`}>
          {text}
        </span>
      </div>
      {active && (
        <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
          <button onClick={onDelete} className="text-gray-400 hover:text-gray-600"><Trash2 size={16} /></button>
          <button className="text-[#5b61f4] bg-white rounded-full p-1 shadow-sm"><Edit2 size={14} /></button>
        </div>
      )}
    </div>
  );
};

export default function ChatUI() {
  const pathname = usePathname();
  
  // Auth State
  const [user, setUser] = useState<any>(null);
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(true);

  const [activeTab, setActiveTab] = useState<"chat" | "documents">("chat");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  
  // Threads State
  const [threads, setThreads] = useState<Thread[]>([]);
  const [threadId, setThreadId] = useState<string>(() => getThreadIdFromPath(pathname));
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const threadIdRef = useRef(threadId);
  const sendAbortRef = useRef<AbortController | null>(null);
  const messagesFetchIdRef = useRef(0);

  threadIdRef.current = threadId;
  
  // Document browser (Google Drive-style)
  const [documents, setDocuments] = useState<any[]>([]);
  const [browseFolders, setBrowseFolders] = useState<DocumentFolder[]>([]);
  const [currentFolderId, setCurrentFolderId] = useState<number | null>(null);
  const [breadcrumb, setBreadcrumb] = useState<BreadcrumbItem[]>([]);
  const [isLoadingBrowse, setIsLoadingBrowse] = useState(false);
  
  // Sync State
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<{type: "success" | "error" | null, message: string}>({type: null, message: ""});
  // Chunk Modal State
  const [selectedChunk, setSelectedChunk] = useState<any>(null);
  const [isChunkModalOpen, setIsChunkModalOpen] = useState(false);
  const [isLoadingChunk, setIsLoadingChunk] = useState(false);

  const fetchChunk = async (chunkId: string) => {
    setIsLoadingChunk(true);
    setIsChunkModalOpen(true);
    try {
      const response = await fetch(`${API_BASE}/chunk/${chunkId}`, {
        credentials: "include",
      });
      if (response.ok) {
        const data = await response.json();
        if (data.status === "success") {
          setSelectedChunk(data.data);
        } else {
          setSelectedChunk({ error: "Chunk not found" });
        }
      }
    } catch (error) {
      console.error("Error fetching chunk:", error);
      setSelectedChunk({ error: "Failed to fetch chunk" });
    } finally {
      setIsLoadingChunk(false);
    }
  };

  const loadCurrentDirectory = async () => {
    setIsLoadingBrowse(true);
    try {
      const parentQuery =
        currentFolderId != null ? `?parent_id=${currentFolderId}` : "";
      const foldersRes = await fetch(`${API_BASE}/folders${parentQuery}`, {
        credentials: "include",
      });
      if (foldersRes.ok) {
        const foldersData = await foldersRes.json();
        if (foldersData.status === "success") {
          setBrowseFolders(foldersData.data || []);
        }
      }

      if (currentFolderId != null) {
        const [breadcrumbRes, docsRes] = await Promise.all([
          fetch(`${API_BASE}/folders/${currentFolderId}/breadcrumb`, {
            credentials: "include",
          }),
          fetch(`${API_BASE}/documents?folder_id=${currentFolderId}`, {
            credentials: "include",
          }),
        ]);
        if (breadcrumbRes.ok) {
          const breadcrumbData = await breadcrumbRes.json();
          if (breadcrumbData.status === "success") {
            setBreadcrumb(breadcrumbData.data || []);
          }
        }
        if (docsRes.ok) {
          const docsData = await docsRes.json();
          if (docsData.status === "success") {
            setDocuments(docsData.data || []);
          }
        }
      } else {
        setBreadcrumb([]);
        setDocuments([]);
      }
    } catch (error) {
      console.error("Error loading directory:", error);
    } finally {
      setIsLoadingBrowse(false);
    }
  };

  const openFolder = (folderId: number) => {
    setCurrentFolderId(folderId);
  };

  const navigateToFolder = (folderId: number | null) => {
    setCurrentFolderId(folderId);
  };

  useEffect(() => {
    if (activeTab === "documents") {
      loadCurrentDirectory();
    }
  }, [activeTab, currentFolderId]);

  const handleSync = async () => {
    setIsSyncing(true);
    setSyncStatus({ type: null, message: "" });
    try {
      const response = await fetch(`${API_BASE}/sync`, { method: "POST", credentials: "include" });
      const data = await response.json();
      if (data.status === "success") {
        const d = data.data;
        const parts: string[] = [];
        if (d.new > 0) parts.push(`${d.new} new`);
        if (d.updated > 0) parts.push(`${d.updated} updated`);
        if (d.deleted > 0) parts.push(`${d.deleted} deleted`);
        if (d.skipped > 0) parts.push(`${d.skipped} unchanged`);
        if (d.stopped_by_rate_limit) parts.push("⚠ stopped by rate limit");
        setSyncStatus({ type: "success", message: `Sync complete: ${parts.join(", ") || "no changes"}` });
        loadCurrentDirectory();
      } else {
        setSyncStatus({ type: "error", message: data.message || "Sync failed" });
      }
    } catch (error) {
      setSyncStatus({ type: "error", message: "Failed to sync. Is the backend running?" });
    } finally {
      setIsSyncing(false);
    }
  };

  useEffect(() => {
    const onPopState = () => {
      const id = getThreadIdFromPath(window.location.pathname);
      setThreadId(id);
      setMessages([]);
      setActiveTab("chat");
    };

    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    const checkSession = async () => {
      try {
        const response = await fetch(`${API_BASE}/auth/me`, {
          credentials: "include",
        });
        if (!response.ok) {
          setUser(null);
          setUserProfile(null);
          setThreads([]);
          return;
        }

        const data = await response.json();
        if (data.status === "success" && data.data) {
          setUser(data.data);
          setUserProfile(data.data);
          await fetchThreads();
        }
      } catch (error) {
        console.error("Error checking session:", error);
        setUser(null);
        setUserProfile(null);
        setThreads([]);
      } finally {
        setIsAuthLoading(false);
      }
    };

    checkSession();
  }, []);

  const fetchThreads = async () => {
    try {
      const response = await fetch(`${API_BASE}/threads`, {
        credentials: "include",
      });
      if (!response.ok) {
        return;
      }
      const data = await response.json();
      if (data.status === "success") {
        setThreads(data.data || []);
      }
    } catch (error) {
      console.error('Error fetching threads:', error);
    }
  };

  const handleDeleteThread = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this conversation?")) return;
    
    try {
      const response = await fetch(`${API_BASE}/chat/conversation/${id}`, {
        method: "DELETE",
        credentials: "include",
      });
      
      if (response.ok) {
        // Refresh the list
        await fetchThreads();
        if (threadId === id) {
          startNewChat();
        }
      } else {
        alert("Failed to delete conversation");
      }
    } catch (error) {
      console.error("Error deleting conversation:", error);
      alert("Error deleting conversation");
    }
  };

  const loadThread = (id: string) => {
    if (id === threadId) return;
    sendAbortRef.current?.abort();
    sendAbortRef.current = null;
    messagesFetchIdRef.current += 1;
    setIsSending(false);
    setThreadId(id);
    setMessages([]);
    setActiveTab("chat");
    updateThreadUrl(id);
  };

  useEffect(() => {
    const fetchMessages = async () => {
      if (!threadId) {
        setMessages([]);
        return;
      }
      if (isSending) return;

      const fetchId = ++messagesFetchIdRef.current;
      setIsLoadingMessages(true);
      try {
        const response = await fetch(`${API_BASE}/chat/conversation/${threadId}`, {
          credentials: "include",
        });
        if (response.ok) {
          const data = await response.json();
          if (
            data.status === "success" &&
            threadIdRef.current === threadId &&
            fetchId === messagesFetchIdRef.current
          ) {
            const loadedMessages = (data.data || [])
              .map((msg: any) => ({
                id: msg.id ? msg.id.toString() : crypto.randomUUID(),
                role: (msg.role === "assistant" ? "ai" : msg.role) as "user" | "ai",
                content: msg.content,
                created_at: msg.created_at ?? "",
              }))
              .sort((a: { created_at: string; id: string }, b: { created_at: string; id: string }) => {
                if (a.created_at && b.created_at) {
                  return a.created_at.localeCompare(b.created_at);
                }
                return Number(a.id) - Number(b.id);
              })
              .map(({ id, role, content }: { id: string; role: "user" | "ai"; content: string }) => ({
                id,
                role,
                content,
              }));
            setMessages(loadedMessages);
          }
        }
      } catch (error) {
        console.error('Error loading messages:', error);
      } finally {
        if (threadIdRef.current === threadId && fetchId === messagesFetchIdRef.current) {
          setIsLoadingMessages(false);
        }
      }
    };

    fetchMessages();
  }, [threadId, isSending]);

  const handleLogin = async () => {
    window.location.href = `${API_BASE}/auth/login?return_to=${encodeURIComponent(window.location.origin + window.location.pathname)}`;
  };

  const handleLogout = async () => {
    await fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
    setUser(null);
    setUserProfile(null);
    setThreads([]);
    setMessages([]);
    startNewChat();
    window.location.href = "/";
  };

  const startNewChat = () => {
    sendAbortRef.current?.abort();
    sendAbortRef.current = null;
    setIsSending(false);
    setThreadId("");
    setMessages([]);
    updateThreadUrl("");
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isSending) return;

    let currentThreadId = threadId;
    const isNewThread = !currentThreadId;
    if (isNewThread) {
      currentThreadId = crypto.randomUUID();
    }

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: input.trim(),
    };

    sendAbortRef.current?.abort();
    const abortController = new AbortController();
    sendAbortRef.current = abortController;

    messagesFetchIdRef.current += 1;
    setThreadId(currentThreadId);
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsSending(true);

    if (isNewThread) {
      window.history.replaceState(null, "", `/c/${currentThreadId}`);
    }

    try {
      const response = await fetch(`${API_BASE}/chat/complete`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        signal: abortController.signal,
        body: JSON.stringify({
          thread_id: currentThreadId,
          message: userMessage.content,
          bot_id: "default_bot",
          sync_request: true,
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to communicate with backend");
      }

      const data = await response.json();

      if (isNewThread) {
        await fetchThreads();
      }
      
      if (threadIdRef.current !== currentThreadId) return;

      let aiContent = "No response received";
      if (typeof data.response === "string") {
        aiContent = data.response;
      } else if (data.response && typeof data.response === "object") {
        aiContent = data.response.content || JSON.stringify(data.response);
      }

      const aiMessage: Message = {
        id: crypto.randomUUID(),
        role: "ai",
        content: aiContent,
      };

      setMessages((prev) => [...prev, aiMessage]);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      console.error("Error sending message:", error);
      if (threadIdRef.current !== currentThreadId) return;

      const errorMessage: Message = {
        id: crypto.randomUUID(),
        role: "ai",
        content: "Sorry, I encountered an error. Is the backend running?",
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      if (sendAbortRef.current === abortController) {
        sendAbortRef.current = null;
      }
      if (threadIdRef.current === currentThreadId) {
        setIsSending(false);
      }
    }
  };



  if (isAuthLoading) {
    return (
      <div className="w-full h-screen flex items-center justify-center bg-white">
        <div className="w-8 h-8 border-2 border-[#5b61f4]/30 border-t-[#5b61f4] rounded-full animate-spin"></div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="w-full h-screen flex items-center justify-center bg-gray-50">
        <div className="bg-white p-8 rounded-2xl shadow-xl max-w-md w-full text-center">
          <div className="w-16 h-16 bg-blue-50 rounded-full flex items-center justify-center mx-auto mb-6 text-[#5b61f4]">
            <Brain size={32} />
          </div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Menas HR Chatbot</h1>
          <p className="text-gray-500 mb-8">Please sign in to access the HR assistant.</p>
          <button 
            onClick={handleLogin}
            className="w-full bg-[#5b61f4] hover:bg-[#4b51e4] text-white font-medium py-3 px-4 rounded-xl transition-colors shadow-md flex items-center justify-center gap-2"
          >
            Sign in with Microsoft
          </button>
        </div>
      </div>
    );
  }

  return (
    <main className="w-full h-full flex overflow-hidden bg-white">
      
      {/* Sidebar */}
      <div className="w-[320px] flex-shrink-0 flex flex-col h-full bg-[#fcfcfc] border-r border-gray-100 p-6 z-10 relative">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-xl font-bold tracking-tight text-gray-900">Menas HR Chatbot</h1>
        </div>
        
        {/* Actions */}
        <div className="flex gap-3 mb-6">
          <button 
            onClick={() => {
              setActiveTab("chat");
              startNewChat();
            }}
            className="flex-1 bg-[#5b61f4] hover:bg-[#4b51e4] text-white rounded-full py-3 px-4 flex items-center justify-center gap-2 font-medium transition-colors shadow-md shadow-blue-500/20"
          >
            <Plus size={20} />
            <span>New chat</span>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex bg-gray-100 p-1 rounded-xl mb-6">
          <button 
            onClick={() => setActiveTab("chat")}
            className={`flex-1 py-2 text-sm font-medium rounded-lg transition-colors flex items-center justify-center gap-2 ${activeTab === 'chat' ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
          >
            <MessageSquare size={16} /> Chat
          </button>
          <button 
            onClick={() => setActiveTab("documents")}
            className={`flex-1 py-2 text-sm font-medium rounded-lg transition-colors flex items-center justify-center gap-2 ${activeTab === 'documents' ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
          >
            <FileText size={16} /> Documents
          </button>
        </div>

        {/* History List (Only show in Chat tab) */}
        {activeTab === "chat" ? (
          <div className="flex-1 overflow-y-auto pr-2 space-y-8 scrollbar-hide">
            <div>
              <div className="flex items-center justify-between mb-3 px-2">
                <h2 className="text-[11px] font-bold text-gray-400 uppercase tracking-wider">Your Conversations</h2>
              </div>
              <div className="space-y-1">
                {threads.map(thread => (
                  <HistoryItem 
                    key={thread.id} 
                    text={thread.title || `Chat ${thread.id.slice(0, 6)}...`} 
                    active={threadId === thread.id} 
                    onClick={() => loadThread(thread.id)}
                    onDelete={(e) => handleDeleteThread(thread.id, e)}
                  />
                ))}
                {threads.length === 0 && (
                  <p className="text-xs text-gray-500 px-2">No conversations yet.</p>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto pr-2">
            <div className="flex items-center justify-between mb-3 px-2">
              <h2 className="text-[11px] font-bold text-gray-400 uppercase tracking-wider">Document Management</h2>
            </div>
            <p className="text-xs text-gray-500 px-2 leading-relaxed">
              Documents are synced automatically from SharePoint every 5 minutes.
            </p>
          </div>
        )}

        {/* Footer Actions */}
        <div className="pt-4 space-y-3 mt-4 bg-[#fcfcfc] relative z-20">
          <button className="w-full flex items-center gap-3 px-4 py-3 rounded-2xl hover:bg-gray-50 text-gray-700 font-medium transition-colors border border-gray-100 bg-white">
            <div className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center">
              <Settings size={18} className="text-gray-600" />
            </div>
            <span className="text-sm">Settings</span>
          </button>
          <div className="w-full flex items-center justify-between px-4 py-3 rounded-2xl border border-gray-100 bg-white">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-blue-100 text-[#5b61f4] flex items-center justify-center font-bold text-xs">
                {userProfile?.name?.charAt(0) || user?.email?.charAt(0) || 'U'}
              </div>
              <div className="flex flex-col">
                <span className="font-medium text-sm text-gray-800 truncate max-w-[120px]">
                  {userProfile?.name || user?.email || 'User'}
                </span>
                <span className="text-[10px] text-gray-500 uppercase">{userProfile?.role || 'user'}</span>
              </div>
            </div>
            <button 
              onClick={handleLogout}
              className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
              title="Sign out"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col h-full bg-white relative">

        {activeTab === "documents" ? (
          <div className="flex-1 overflow-y-auto p-6 md:p-10">
            <div className="max-w-5xl mx-auto">
              <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
                <div>
                  <h2 className="text-2xl font-bold text-gray-900">Documents</h2>
                  <p className="text-gray-500 text-sm mt-1">
                    Browse folders and documents synced from SharePoint
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  {userProfile?.role === "admin" && (
                    <button
                      type="button"
                      onClick={handleSync}
                      disabled={isSyncing}
                      className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#5b61f4] text-white text-sm font-medium hover:bg-[#4b51e4] disabled:bg-gray-400 transition-colors shadow-md shadow-blue-500/20"
                    >
                      {isSyncing ? (
                        <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      ) : (
                        <CloudDownload size={18} />
                      )}
                      {isSyncing ? "Syncing…" : "Sync from SharePoint"}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={loadCurrentDirectory}
                    className="p-2.5 rounded-xl border border-gray-200 text-gray-500 hover:text-[#5b61f4] hover:bg-gray-50 transition-colors"
                    title="Refresh"
                  >
                    <RefreshCw size={18} className={isLoadingBrowse ? "animate-spin" : ""} />
                  </button>
                </div>
                {syncStatus.message && (
                  <p className={`w-full text-sm ${syncStatus.type === "error" ? "text-red-600" : "text-green-600"}`}>
                    {syncStatus.message}
                  </p>
                )}
              </div>

              <nav className="flex items-center gap-1 flex-wrap text-sm mb-6 px-1">
                <button
                  type="button"
                  onClick={() => navigateToFolder(null)}
                  className={`flex items-center gap-1.5 px-2 py-1 rounded-lg transition-colors ${
                    currentFolderId == null ? "text-[#5b61f4] font-semibold" : "text-gray-600 hover:bg-gray-100"
                  }`}
                >
                  <Home size={16} />
                  My Drive
                </button>
                {breadcrumb.map((item, index) => (
                  <React.Fragment key={item.id}>
                    <ChevronRight size={14} className="text-gray-300 flex-shrink-0" />
                    <button
                      type="button"
                      onClick={() => navigateToFolder(item.id)}
                      className={`px-2 py-1 rounded-lg transition-colors truncate max-w-[160px] ${
                        index === breadcrumb.length - 1
                          ? "text-[#5b61f4] font-semibold"
                          : "text-gray-600 hover:bg-gray-100"
                      }`}
                    >
                      {item.name}
                    </button>
                  </React.Fragment>
                ))}
              </nav>

              {isLoadingBrowse ? (
                <div className="flex justify-center py-24">
                  <div className="w-8 h-8 border-2 border-[#5b61f4]/30 border-t-[#5b61f4] rounded-full animate-spin" />
                </div>
              ) : browseFolders.length === 0 && documents.length === 0 ? (
                <div className="text-center py-20 bg-gray-50/80 rounded-2xl border border-dashed border-gray-200">
                  <Folder size={40} className="mx-auto text-gray-300 mb-3" />
                  <p className="text-gray-600 font-medium">This folder is empty</p>
                  <p className="text-gray-400 text-sm mt-1">
                    Documents are synced from SharePoint automatically.
                  </p>
                </div>
              ) : (
                <div className="rounded-xl border border-gray-100 bg-white overflow-hidden divide-y divide-gray-100">
                  {browseFolders.map((folder) => (
                    <div
                      key={folder.id}
                      role="button"
                      tabIndex={0}
                      onClick={() => openFolder(folder.id)}
                      onKeyDown={(e) => e.key === "Enter" && openFolder(folder.id)}
                      className="group flex items-center gap-3 px-4 py-3 hover:bg-gray-50 transition-colors cursor-pointer"
                    >
                      <div className="w-9 h-9 rounded-lg bg-amber-50 text-amber-500 flex items-center justify-center flex-shrink-0">
                        <Folder size={18} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-gray-800 truncate" title={folder.name}>
                          {folder.name}
                        </p>
                        <p className="text-xs text-gray-400">{getFolderMeta(folder)}</p>
                      </div>
                      <span className="text-xs text-gray-400 hidden sm:inline">Folder</span>
                    </div>
                  ))}
                  {documents.map((doc) => (
                    <div
                      key={doc.id}
                      className="group flex items-center gap-3 px-4 py-3 hover:bg-gray-50 transition-colors"
                    >
                      <div className="w-9 h-9 rounded-lg bg-red-50 text-red-500 flex items-center justify-center flex-shrink-0">
                        <FileText size={18} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-gray-800 truncate" title={doc.title}>
                          {doc.title}
                        </p>
                        <p className="text-xs text-gray-400">
                          {(doc.source_type || "pdf").toUpperCase()} · {new Date(doc.created_at).toLocaleDateString()}
                        </p>
                      </div>
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <a
                          href={`${API_BASE}/documents/${doc.id}/view`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-2 text-gray-400 hover:text-[#5b61f4] hover:bg-blue-50 rounded-lg"
                          title="View"
                        >
                          <Search size={16} />
                        </a>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>


          </div>
        ) : (
          <div className="flex-1 overflow-y-auto p-8 md:p-12 pb-32">
          <div className="max-w-4xl mx-auto space-y-10">
            
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center mt-32 space-y-6">
                 <div className="w-20 h-20 bg-pink-50 rounded-full flex items-center justify-center">
                    <Brain size={40} className="text-pink-400" />
                 </div>
                 <h2 className="text-2xl font-bold text-gray-800">How can I help you today?</h2>
                 <p className="text-gray-500 text-center max-w-md">Start a conversation by typing a message below. I can assist you with HR inquiries, tasks, and more.</p>
              </div>
            ) : (
              messages.map((msg, index) => (
                <div key={msg.id}>
                  {msg.role === "user" ? (
                    // User Message
                    <div className="flex flex-row-reverse gap-4 w-full">
                      <div className="w-9 h-9 rounded-full bg-blue-100 text-[#5b61f4] flex items-center justify-center font-bold text-sm shadow-sm flex-shrink-0">
                        {userProfile?.name?.charAt(0) || user?.email?.charAt(0) || 'U'}
                      </div>
                      <div className="flex-1 pt-1 text-right">
                        <p className="text-gray-800 font-medium text-[15px]">{msg.content}</p>
                      </div>
                    </div>
                  ) : (
                    // AI Message
                    <div className="flex gap-4">
                      <div className="w-9 h-9 rounded-full bg-gray-50 flex items-center justify-center flex-shrink-0 text-[#5b61f4] font-bold text-xs relative shadow-sm border border-gray-100">
                        AI
                        <div className="absolute -bottom-1 -right-1 bg-white rounded-full">
                          <CheckCircle2 size={14} className="text-[#5b61f4] fill-white" />
                        </div>
                      </div>
                      <div className="flex-1 space-y-5 text-[15px] text-gray-700 leading-relaxed">
                        <div className="flex items-center gap-1">
                          <p className="font-semibold text-[#5b61f4] text-xs uppercase tracking-wide">Menas AI-HR chatbot</p>
                          <CheckCircle2 size={12} className="text-blue-400" />
                        </div>
                        
                        <div className="prose prose-blue max-w-none prose-p:leading-relaxed prose-pre:bg-gray-50 prose-pre:text-gray-800 prose-pre:border prose-pre:border-gray-200 prose-headings:font-semibold prose-a:text-blue-600">
                          <ReactMarkdown
                            components={{
                              a: ({ node, href, children, ...props }) => {
                                if (href && !href.startsWith('http')) {
                                  return (
                                    <button 
                                      onClick={() => fetchChunk(href)}
                                      className="inline-flex items-center justify-center h-5 px-2 rounded-full bg-blue-100 text-[#5b61f4] text-[11px] font-bold mx-1 hover:bg-blue-200 transition-colors align-middle whitespace-nowrap"
                                      title="View source document"
                                    >
                                      <FileText size={10} className="mr-1 inline-block" />
                                      {children}
                                    </button>
                                  );
                                }
                                return <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>;
                              }
                            }}
                          >
                            {msg.content}
                          </ReactMarkdown>
                        </div>

                        <div className="flex items-center justify-between mt-8 pt-4">
                          <div className="flex items-center gap-5 text-gray-400">
                            <button className="hover:text-[#5b61f4] hover:bg-blue-50 p-2 rounded-lg transition-colors"><ThumbsUp size={18} /></button>
                            <button className="hover:text-red-500 hover:bg-red-50 p-2 rounded-lg transition-colors"><ThumbsDown size={18} /></button>
                            <button className="hover:text-gray-600 hover:bg-gray-100 p-2 rounded-lg transition-colors"><Copy size={18} /></button>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Divider - only show if it's not the last message */}
                  {index < messages.length - 1 && (
                    <div className="h-px w-full bg-gray-100 my-6"></div>
                  )}
                </div>
              ))
            )}

            {isSending && (
              <div className="flex gap-4">
                <div className="w-9 h-9 rounded-full bg-gray-50 flex items-center justify-center flex-shrink-0 text-[#5b61f4] font-bold text-xs relative shadow-sm border border-gray-100">
                  AI
                </div>
                <div className="flex-1 pt-2">
                  <div className="flex gap-1.5 items-center">
                    <div className="w-2 h-2 bg-[#5b61f4] rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                    <div className="w-2 h-2 bg-[#5b61f4] rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                    <div className="w-2 h-2 bg-[#5b61f4] rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>
        )}

        {/* Input Area */}
        {activeTab === "chat" && (
          <div className="absolute bottom-8 left-0 right-0 px-8 flex justify-center w-full z-10 bg-gradient-to-t from-white via-white pt-8">
            <div className="w-full max-w-3xl bg-white rounded-full shadow-[0_8px_30px_rgb(0,0,0,0.08)] border border-gray-100 p-2 flex items-center">
              <div className="w-10 h-10 rounded-full flex items-center justify-center ml-1 bg-pink-50 flex-shrink-0">
                <Brain size={22} className="text-pink-400" />
              </div>
              <input 
                type="text" 
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSend();
                }}
                placeholder="What's in your mind?.." 
                className="flex-1 bg-transparent border-none focus:outline-none px-4 text-gray-700 placeholder-gray-400 font-medium text-[15px]"
              />
              <button 
                onClick={handleSend}
                disabled={isSending || !input.trim()}
                className="w-11 h-11 bg-[#5b61f4] text-white rounded-full flex items-center justify-center flex-shrink-0 hover:bg-[#4b51e4] disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors shadow-md"
              >
                <Send size={18} className="ml-1" />
              </button>
            </div>
          </div>
        )}
      </div>
      {/* Chunk Modal */}
      {isChunkModalOpen && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between p-4 border-b border-gray-100 bg-gray-50/50">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-[#5b61f4]">
                  <FileText size={16} />
                </div>
                <h3 className="font-semibold text-gray-900">Source Reference</h3>
              </div>
              <button 
                onClick={() => setIsChunkModalOpen(false)}
                className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-colors"
              >
                <X size={20} />
              </button>
            </div>
            
            <div className="p-6 overflow-y-auto flex-1">
              {isLoadingChunk ? (
                <div className="flex flex-col items-center justify-center py-12 gap-4">
                  <div className="w-8 h-8 border-2 border-[#5b61f4]/30 border-t-[#5b61f4] rounded-full animate-spin"></div>
                  <p className="text-sm text-gray-500 font-medium">Loading reference content...</p>
                </div>
              ) : selectedChunk?.error ? (
                <div className="text-center py-12">
                  <div className="w-12 h-12 bg-red-50 text-red-500 rounded-full flex items-center justify-center mx-auto mb-3">
                    <X size={24} />
                  </div>
                  <p className="text-red-600 font-medium">{selectedChunk.error}</p>
                </div>
              ) : selectedChunk ? (
                <div className="space-y-6">
                  <div className="flex flex-wrap gap-2 mb-4">
                    {selectedChunk.metadata?.title && (
                      <span className="px-3 py-1 bg-gray-100 text-gray-700 text-xs font-medium rounded-full">
                        Document: {selectedChunk.metadata.title}
                      </span>
                    )}
                  </div>
                  <div className="bg-gray-50 rounded-xl p-5 border border-gray-100">
                    <p className="text-gray-800 text-[15px] leading-relaxed whitespace-pre-wrap font-serif">
                      {selectedChunk.content}
                    </p>
                  </div>
                  {(selectedChunk.metadata?.document_id || selectedChunk.metadata?.file_url) && (
                    <a
                      href={selectedChunk.metadata.document_id ? `${API_BASE}/documents/${selectedChunk.metadata.document_id}/view` : selectedChunk.metadata.file_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 text-sm font-medium text-[#5b61f4] hover:underline"
                    >
                      <FileText size={16} />
                      Open original PDF
                    </a>
                  )}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
