import { Routes, Route, Navigate } from 'react-router-dom';
import { AppSidebar } from '@/components/AppSidebar';
import { CreateClusterForm } from '@/components/CreateClusterForm/CreateClusterForm';
import { DeleteClusterPanel } from '@/components/DeleteClusterPanel/DeleteClusterPanel';
import { ClusterStatusPanel } from '@/components/ClusterStatusPanel';
import { useAuth } from '@/contexts/AuthContext';

export default function Dashboard() {
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="min-h-screen w-full bg-background">
      <AppSidebar />

      {/* offset for fixed sidebar */}
      <main className="pl-64 min-h-screen overflow-auto">
        <div className="w-full max-w-none py-8 px-6">
          <Routes>
            <Route index element={<ClusterStatusPanel />} />
            <Route path="create" element={<CreateClusterForm />} />
            <Route path="delete" element={<DeleteClusterPanel />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
