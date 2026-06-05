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
  Upload,
  X,
  LogOut,
  Folder,
  FolderPlus,
  ChevronRight,
  Home,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { usePathname } from "next/navigation";
import { supabase } from "@/lib/supabase";
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
  
  // Document Upload State
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadTitle, setUploadTitle] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState("");
  const [uploadStatus, setUploadStatus] = useState<{type: "success" | "error" | null, message: string}>({type: null, message: ""});
  
  // Document browser (Google Drive-style)
  const [documents, setDocuments] = useState<any[]>([]);
  const [browseFolders, setBrowseFolders] = useState<DocumentFolder[]>([]);
  const [currentFolderId, setCurrentFolderId] = useState<number | null>(null);
  const [breadcrumb, setBreadcrumb] = useState<BreadcrumbItem[]>([]);
  const [isLoadingBrowse, setIsLoadingBrowse] = useState(false);
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [isNewFolderModalOpen, setIsNewFolderModalOpen] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [isCreatingFolder, setIsCreatingFolder] = useState(false);
  // Chunk Modal State
  const [selectedChunk, setSelectedChunk] = useState<any>(null);
  const [isChunkModalOpen, setIsChunkModalOpen] = useState(false);
  const [isLoadingChunk, setIsLoadingChunk] = useState(false);

  const fetchChunk = async (chunkId: string) => {
    setIsLoadingChunk(true);
    setIsChunkModalOpen(true);
    try {
      const response = await fetch(`${API_BASE}/chunk/${chunkId}`);
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
      const foldersRes = await fetch(`${API_BASE}/folders${parentQuery}`);
      if (foldersRes.ok) {
        const foldersData = await foldersRes.json();
        if (foldersData.status === "success") {
          setBrowseFolders(foldersData.data || []);
        }
      }

      if (currentFolderId != null) {
        const [breadcrumbRes, docsRes] = await Promise.all([
          fetch(`${API_BASE}/folders/${currentFolderId}/breadcrumb`),
          fetch(`${API_BASE}/documents?folder_id=${currentFolderId}`),
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

  const handleCreateFolder = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = newFolderName.trim();
    if (!name) return;

    setIsCreatingFolder(true);
    try {
      const response = await fetch(`${API_BASE}/folders`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          parent_id: currentFolderId,
          created_by: userProfile?.name || user?.email || "admin",
        }),
      });
      const data = await response.json();
      if (data.status !== "success") {
        throw new Error(data.message || "Failed to create folder");
      }
      setNewFolderName("");
      setIsNewFolderModalOpen(false);
      loadCurrentDirectory();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to create folder";
      alert(message);
    } finally {
      setIsCreatingFolder(false);
    }
  };

  const handleDeleteFolder = async (folder: DocumentFolder, e: React.MouseEvent) => {
    e.stopPropagation();
    if (folder.slug === "general" && folder.parent_id == null) {
      alert("The General folder cannot be deleted.");
      return;
    }
    if (!confirm(`Delete folder "${folder.name}"? It must be empty.`)) return;

    try {
      const response = await fetch(`${API_BASE}/folders/${folder.id}`, { method: "DELETE" });
      const data = await response.json();
      if (data.status !== "success") {
        alert(data.message || "Failed to delete folder");
        return;
      }
      loadCurrentDirectory();
    } catch (error) {
      console.error("Error deleting folder:", error);
      alert("Failed to delete folder");
    }
  };

  useEffect(() => {
    if (activeTab === "documents" && userProfile?.role === "admin") {
      loadCurrentDirectory();
    }
  }, [activeTab, userProfile, currentFolderId]);

  const handleDeleteDocument = async (id: string) => {
    if (!confirm("Are you sure you want to delete this document?")) return;
    
    try {
      const response = await fetch(`${API_BASE}/document/${id}`, {
        method: "DELETE",
      });
      
      if (response.ok) {
        loadCurrentDirectory();
      } else {
        alert("Failed to delete document");
      }
    } catch (error) {
      console.error("Error deleting document:", error);
      alert("Error deleting document");
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
      const { data: { session } } = await supabase.auth.getSession();
      setUser(session?.user || null);
      if (session?.user) {
        fetchUserProfile(session.user.id);
        fetchThreads(session.user.id);
      } else {
        setIsAuthLoading(false);
      }
    };

    checkSession();

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user || null);
      if (session?.user) {
        fetchUserProfile(session.user.id);
        fetchThreads(session.user.id);
      } else {
        setUserProfile(null);
        setThreads([]);
        setIsAuthLoading(false);
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  const fetchUserProfile = async (userId: string) => {
    try {
      const { data, error } = await supabase
        .from('users')
        .select('*')
        .eq('id', userId)
        .single();
      
      if (error) throw error;
      setUserProfile(data);
    } catch (error) {
      console.error('Error fetching user profile:', error);
    } finally {
      setIsAuthLoading(false);
    }
  };

  const handleDeleteThread = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this conversation?")) return;
    
    try {
      const response = await fetch(`http://localhost:8000/chat/conversation/${id}`, {
        method: "DELETE",
      });
      
      if (response.ok) {
        // Refresh the list
        if (user) {
          fetchThreads(user.id);
        }
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

  const fetchThreads = async (userId: string) => {
    try {
      const { data, error } = await supabase
        .from('threads')
        .select('*')
        .eq('user_id', userId)
        .order('created_at', { ascending: false });
      
      if (error) throw error;
      setThreads(data || []);
    } catch (error) {
      console.error('Error fetching threads:', error);
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
        const response = await fetch(`http://localhost:8000/chat/conversation/${threadId}`);
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
    await supabase.auth.signInWithOAuth({
      provider: 'azure',
      options: {
        scopes: 'email profile openid',
      },
    });
  };

  const handleLogout = async () => {
    await supabase.auth.signOut();
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

      if (user) {
        await supabase.from('threads').insert({
          id: currentThreadId,
          user_id: user.id,
          title: userMessage.content.slice(0, 30) + (userMessage.content.length > 30 ? '...' : '')
        });
        fetchThreads(user.id);
      }
    }

    try {
      const response = await fetch("http://localhost:8000/chat/complete", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
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

  const handleFileUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (uploadFiles.length === 0 || currentFolderId == null) return;

    setIsUploading(true);
    setUploadStatus({ type: null, message: "" });
    setUploadProgress(`Uploading 0/${uploadFiles.length}…`);

    try {
      if (uploadFiles.length === 1 && uploadTitle.trim()) {
        const formData = new FormData();
        formData.append("file", uploadFiles[0]);
        formData.append("title", uploadTitle.trim());
        formData.append("owner_id", "default_user");
        formData.append("folder_id", String(currentFolderId));
        formData.append("source_type", "pdf");

        setUploadProgress(`Uploading 1/1: ${uploadFiles[0].name}`);
        const response = await fetch(`${API_BASE}/document/create`, {
          method: "POST",
          body: formData,
        });
        const data = await response.json();
        if (!response.ok || data.status !== "success") {
          throw new Error(data.message || "Upload failed");
        }
        const replacedNote = data.replaced ? " (replaced existing file)" : "";
        setUploadStatus({
          type: "success",
          message: `Uploaded 1 document successfully${replacedNote}.`,
        });
      } else {
        const formData = new FormData();
        uploadFiles.forEach((file) => formData.append("files", file));
        formData.append("owner_id", "default_user");
        formData.append("folder_id", String(currentFolderId));
        formData.append("source_type", "pdf");

        setUploadProgress(`Uploading ${uploadFiles.length} file(s)…`);
        const response = await fetch(`${API_BASE}/document/create-batch`, {
          method: "POST",
          body: formData,
        });
        const data = await response.json();
        if (!response.ok || data.status !== "success") {
          const completed = data.completed_count ?? 0;
          const failedFile = data.failed_file ? ` Failed on: ${data.failed_file}.` : "";
          const partial =
            completed > 0
              ? ` ${completed} file(s) uploaded before the error.${failedFile}`
              : failedFile;
          throw new Error((data.message || "Batch upload failed") + partial);
        }
        const replacedCount = (data.data || []).filter((d: { replaced?: boolean }) => d.replaced).length;
        const replacedNote =
          replacedCount > 0 ? ` (${replacedCount} replaced existing file(s))` : "";
        setUploadStatus({
          type: "success",
          message: `Uploaded ${data.completed_count} document(s) successfully${replacedNote}.`,
        });
      }

      setUploadFiles([]);
      setUploadTitle("");
      setUploadProgress("");
      setIsUploadModalOpen(false);
      loadCurrentDirectory();
    } catch (error) {
      console.error("Upload error:", error);
      const message =
        error instanceof Error ? error.message : "Failed to upload documents. Is the backend running?";
      setUploadStatus({ type: "error", message });
    } finally {
      setIsUploading(false);
      setUploadProgress("");
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
          {userProfile?.role === 'admin' && (
            <button 
              onClick={() => setActiveTab("documents")}
              className={`flex-1 py-2 text-sm font-medium rounded-lg transition-colors flex items-center justify-center gap-2 ${activeTab === 'documents' ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
            >
              <FileText size={16} /> Documents
            </button>
          )}
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
              Upload your documents here so the AI can use them as context for your questions.
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
                  <p className="text-gray-500 text-sm mt-1">Browse folders and upload PDFs</p>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <button
                    type="button"
                    onClick={() => setIsNewFolderModalOpen(true)}
                    className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-gray-200 bg-white text-gray-700 text-sm font-medium hover:bg-gray-50 transition-colors"
                  >
                    <FolderPlus size={18} />
                    New folder
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsUploadModalOpen(true)}
                    disabled={currentFolderId == null}
                    title={currentFolderId == null ? "Open a folder to upload" : "Upload PDF"}
                    className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#5b61f4] text-white text-sm font-medium hover:bg-[#4b51e4] disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors shadow-md shadow-blue-500/20"
                  >
                    <Upload size={18} />
                    Upload
                  </button>
                  <button
                    type="button"
                    onClick={loadCurrentDirectory}
                    className="p-2.5 rounded-xl border border-gray-200 text-gray-500 hover:text-[#5b61f4] hover:bg-gray-50 transition-colors"
                    title="Refresh"
                  >
                    <RefreshCw size={18} className={isLoadingBrowse ? "animate-spin" : ""} />
                  </button>
                </div>
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
                    {currentFolderId == null
                      ? "Create a folder or open one to upload files."
                      : "Use Upload to add a PDF here."}
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
                      {!(folder.slug === "general" && folder.parent_id == null) && (
                        <button
                          type="button"
                          onClick={(e) => handleDeleteFolder(folder, e)}
                          className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity"
                          title="Delete folder"
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
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
                          PDF · {new Date(doc.created_at).toLocaleDateString()}
                        </p>
                      </div>
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <a
                          href={doc.file_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-2 text-gray-400 hover:text-[#5b61f4] hover:bg-blue-50 rounded-lg"
                          title="View"
                        >
                          <Search size={16} />
                        </a>
                        <button
                          type="button"
                          onClick={() => handleDeleteDocument(doc.id)}
                          className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg"
                          title="Delete"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {isNewFolderModalOpen && (
              <div
                className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
                onClick={() => setIsNewFolderModalOpen(false)}
              >
                <div
                  className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-bold text-gray-900">New folder</h3>
                    <button
                      type="button"
                      onClick={() => setIsNewFolderModalOpen(false)}
                      className="p-1 text-gray-400 hover:text-gray-600 rounded-lg"
                    >
                      <X size={20} />
                    </button>
                  </div>
                  <form onSubmit={handleCreateFolder} className="space-y-4">
                    <input
                      type="text"
                      value={newFolderName}
                      onChange={(e) => setNewFolderName(e.target.value)}
                      placeholder="Folder name"
                      autoFocus
                      className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:outline-none focus:ring-2 focus:ring-[#5b61f4]/20 focus:border-[#5b61f4]"
                    />
                    <p className="text-xs text-gray-400">
                      Created inside:{" "}
                      {currentFolderId == null
                        ? "My Drive (root)"
                        : breadcrumb[breadcrumb.length - 1]?.name ?? "current folder"}
                    </p>
                    <div className="flex gap-2 justify-end">
                      <button
                        type="button"
                        onClick={() => setIsNewFolderModalOpen(false)}
                        className="px-4 py-2.5 rounded-xl border border-gray-200 text-gray-600 text-sm font-medium hover:bg-gray-50"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={!newFolderName.trim() || isCreatingFolder}
                        className="px-4 py-2.5 rounded-xl bg-[#5b61f4] text-white text-sm font-medium hover:bg-[#4b51e4] disabled:bg-gray-300"
                      >
                        {isCreatingFolder ? "Creating…" : "Create"}
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            )}

            {isUploadModalOpen && currentFolderId != null && (
              <div
                className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
                onClick={() => !isUploading && setIsUploadModalOpen(false)}
              >
                <div
                  className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-bold text-gray-900">Upload documents</h3>
                    <button
                      type="button"
                      onClick={() => !isUploading && setIsUploadModalOpen(false)}
                      className="p-1 text-gray-400 hover:text-gray-600 rounded-lg"
                    >
                      <X size={20} />
                    </button>
                  </div>
                  <p className="text-xs text-gray-500 mb-4">
                    Uploading to:{" "}
                    <span className="font-medium text-gray-700">
                      {breadcrumb[breadcrumb.length - 1]?.name ?? "folder"}
                    </span>
                  </p>
                  <form onSubmit={handleFileUpload} className="space-y-4">
                    {uploadFiles.length <= 1 && (
                      <div>
                        <label className="text-sm font-semibold text-gray-700">Title (single file)</label>
                        <input
                          type="text"
                          value={uploadTitle}
                          onChange={(e) => setUploadTitle(e.target.value)}
                          placeholder="Document title (optional)"
                          className="mt-1 w-full px-4 py-3 rounded-xl border border-gray-200 focus:outline-none focus:ring-2 focus:ring-[#5b61f4]/20 focus:border-[#5b61f4]"
                        />
                      </div>
                    )}
                    <div className="relative border-2 border-dashed border-gray-300 rounded-xl p-8 text-center hover:bg-gray-50 transition-colors cursor-pointer">
                      <input
                        type="file"
                        accept=".pdf"
                        multiple
                        onChange={(e) => setUploadFiles(Array.from(e.target.files || []))}
                        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                        required={uploadFiles.length === 0}
                      />
                      <Upload size={28} className="mx-auto text-gray-400 mb-2" />
                      <p className="text-sm font-medium text-gray-700">
                        {uploadFiles.length === 0
                          ? "Choose one or more PDFs"
                          : `${uploadFiles.length} file(s) selected`}
                      </p>
                    </div>
                    {uploadFiles.length > 0 && (
                      <ul className="max-h-32 overflow-y-auto text-xs text-gray-600 space-y-1 px-1">
                        {uploadFiles.map((file) => (
                          <li key={`${file.name}-${file.size}`} className="truncate">
                            {file.name}
                          </li>
                        ))}
                      </ul>
                    )}
                    <p className="text-xs text-gray-400">
                      Batch upload stops on the first error. Files with the same name replace the existing document.
                    </p>
                    {uploadProgress && (
                      <p className="text-sm text-[#5b61f4] font-medium">{uploadProgress}</p>
                    )}
                    {uploadStatus.message && (
                      <p
                        className={`text-sm ${
                          uploadStatus.type === "error" ? "text-red-600" : "text-green-600"
                        }`}
                      >
                        {uploadStatus.message}
                      </p>
                    )}
                    <div className="flex gap-2 justify-end">
                      <button
                        type="button"
                        onClick={() => setIsUploadModalOpen(false)}
                        disabled={isUploading}
                        className="px-4 py-2.5 rounded-xl border border-gray-200 text-gray-600 text-sm font-medium hover:bg-gray-50 disabled:opacity-50"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={uploadFiles.length === 0 || isUploading}
                        className="px-4 py-2.5 rounded-xl bg-[#5b61f4] text-white text-sm font-medium hover:bg-[#4b51e4] disabled:bg-gray-300 flex items-center gap-2"
                      >
                        {isUploading && (
                          <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        )}
                        {isUploading ? "Uploading…" : uploadFiles.length > 1 ? `Upload ${uploadFiles.length} files` : "Upload"}
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            )}
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
                  {selectedChunk.metadata?.file_url && (
                    <a
                      href={selectedChunk.metadata.file_url}
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
