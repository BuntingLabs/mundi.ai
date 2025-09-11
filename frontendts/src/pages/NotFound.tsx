// Copyright Bunting Labs, Inc. 2025

import { ArrowLeft, Home } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';

const NotFound = () => {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col items-center justify-center min-h-screen w-full text-center text-white">
      <h1 className="text-8xl font-bold mb-4">404</h1>
      <h2 className="text-2xl font-semibold mb-4">Page Not Found</h2>
      <p className="mb-8">The page you're looking for doesn't exist or has been moved.</p>

      <div className="flex gap-4 justify-center">
        <Button onClick={() => navigate(-1)} variant="outline" className="flex items-center gap-2 cursor-pointer">
          <ArrowLeft className="h-4 w-4" />
          Go Back
        </Button>
        <Button onClick={() => navigate('/')} className="flex items-center gap-2 cursor-pointer">
          <Home className="h-4 w-4" />
          Home
        </Button>
      </div>
    </div>
  );
};

export default NotFound;
