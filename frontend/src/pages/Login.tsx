import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Loader2 } from 'lucide-react';
import { Navigate } from 'react-router-dom';

export default function Login() {
  const { login, isAuthenticated, isLoading } = useAuth();

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      {/* Background Pattern */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute -top-1/2 -right-1/2 w-full h-full bg-gradient-to-bl from-primary/5 to-transparent rounded-full blur-3xl" />
        <div className="absolute -bottom-1/2 -left-1/2 w-full h-full bg-gradient-to-tr from-primary/5 to-transparent rounded-full blur-3xl" />
      </div>

      <Card className="w-full max-w-md relative animate-fade-in">
        <CardHeader className="text-center space-y-4">
          {/* Logo */}
          <div className="mx-auto h-16 w-16 rounded-2xl gradient-openshift-background flex items-center justify-center glow-primary">
          <img
            src="/autoshiftlogo.png"
            alt="AutoShift logo"
            className="h-full w-full object-contain"
          />
        </div>
          
          <div className="space-y-2">
            <CardTitle className="font-display text-2xl">AutoShift</CardTitle>
            <CardDescription>
              Create and manage your OpenShift clusters
            </CardDescription>
          </div>
        </CardHeader>

        <CardContent className="space-y-6">
          <Button
            onClick={login}
            disabled={isLoading}
            className="w-full h-12 gap-3 text-base font-medium"
            size="lg"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-5 w-5 animate-spin" />
                Signing in...
              </>
            ) : (
              <>
                <svg
                  className="h-5 w-5"
                  viewBox="0 0 21 21"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path d="M10 0H0V10H10V0Z" fill="#F25022" />
                  <path d="M21 0H11V10H21V0Z" fill="#7FBA00" />
                  <path d="M10 11H0V21H10V11Z" fill="#00A4EF" />
                  <path d="M21 11H11V21H21V11Z" fill="#FFB900" />
                </svg>
                Sign in with Azure AD
              </>
            )}
          </Button>

        </CardContent>
      </Card>
    </div>
  );
}
