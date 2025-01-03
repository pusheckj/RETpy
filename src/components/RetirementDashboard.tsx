//
// By jacob Pusheck - pusheckj@gmail.com//
//

import React, { useState, useCallback, useMemo } from 'react';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, 
  ResponsiveContainer, AreaChart, Area, ComposedChart, Bar,
  BarChart
} from 'recharts';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Slider } from '@/components/ui/slider';
import { Label } from '@/components/ui/label';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { DollarSign, Percent, Calendar, TrendingUp, Plus, X } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';

const formatCurrency = (value: number | bigint) => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

function generateNormalReturn({ mean, stdDev }: { mean: number; stdDev: number; }) {
  let u1 = Math.random();
  let u2 = Math.random();
  let z = Math.sqrt(-2.0 * Math.log(u1)) * Math.cos(2.0 * Math.PI * u2);
  return mean + stdDev * z;
}

const generateReturns = (years: number, mean: number, stdDev: number) => {
  let returns = [];
  for (let i = 0; i < years; i++) {
    returns.push(generateNormalReturn({ mean: mean / 100, stdDev: stdDev / 100 }));
  }
  return returns;
};

const generateAverageReturns = (params: { lifeExpectancy: number; currentAge: number; accounts: { hsa: { expectedReturn: number; stdDev: number; }; retirement401k: { expectedReturn: number; stdDev: number; }; rothIra: { expectedReturn: number; stdDev: number; }; brokerage: { expectedReturn: number; stdDev: number; }; realEstate: { expectedReturn: number; stdDev: number; }; }; }, iterations = 10000) => {
  const years = params.lifeExpectancy - params.currentAge;
  const aggregatedReturns = {
      hsa: Array(years).fill(0),
      retirement401k: Array(years).fill(0),
      rothIra: Array(years).fill(0),
      brokerage: Array(years).fill(0),
      realEstate: Array(years).fill(0)
  };

  for (let iteration = 0; iteration < iterations; iteration++) {
      const returns = {
          hsa: generateReturns(years, params.accounts.hsa.expectedReturn, params.accounts.hsa.stdDev),
          retirement401k: generateReturns(years, params.accounts.retirement401k.expectedReturn, params.accounts.retirement401k.stdDev),
          rothIra: generateReturns(years, params.accounts.rothIra.expectedReturn, params.accounts.rothIra.stdDev),
          brokerage: generateReturns(years, params.accounts.brokerage.expectedReturn, params.accounts.brokerage.stdDev),
          realEstate: generateReturns(years, params.accounts.realEstate.expectedReturn, params.accounts.realEstate.stdDev)
      };

      Object.keys(returns).forEach((accountType) => {
          for (let year = 0; year < years; year++) {
              aggregatedReturns[accountType][year] += returns[accountType][year];
          }
      });
  }

  // Calculate the average return for each year
  Object.keys(aggregatedReturns).forEach((accountType) => {
      aggregatedReturns[accountType] = aggregatedReturns[accountType].map(
          (total: number) => total / iterations
      );
  });

  return aggregatedReturns;
};

const generateProjections = (params) => {
  const years = params.lifeExpectancy - params.currentAge;
  const retirementYear = params.retirementAge - params.currentAge;
  const averageReturns = generateAverageReturns(params);
  let projections = [];
  let accounts = {
      hsa: params.accounts.hsa.balance,
      retirement401k: params.accounts.retirement401k.balance,
      rothIra: params.accounts.rothIra.balance,
      brokerage: params.accounts.brokerage.balance,
      realEstate: params.accounts.realEstate.balance
  };
  const inflationRate = params.inflationRate / 100;

  for (let i = 0; i < years; i++) {
      const age = params.currentAge + i;
      const isRetired = age >= params.retirementAge;

      Object.keys(accounts).forEach((accountType) => {
          const account = params.accounts[accountType];
          accounts[accountType] *= (1 + averageReturns[accountType][i]);
          if (!isRetired) {
              accounts[accountType] += account.annualContribution * Math.pow(1 + inflationRate, i);
          }
      });

      const totalBalance = Object.values(accounts).reduce((sum, balance) => sum + balance, 0);

      if (isRetired) {
          const inflationAdjustedExpenses = params.annualExpenses * Math.pow(1 + inflationRate, i);
          let remainingWithdrawal = inflationAdjustedExpenses;
          ['hsa', 'retirement401k', 'brokerage', 'rothIra'].forEach((account) => {
              if (remainingWithdrawal > 0) {
                  const withdrawal = Math.min(remainingWithdrawal, accounts[account]);
                  accounts[account] -= withdrawal;
                  remainingWithdrawal -= withdrawal;
              }
          });
      }

      projections.push({
          age,
          year: new Date().getFullYear() + i,
          totalBalance,
          hsaBalance: accounts.hsa,
          retirement401kBalance: accounts.retirement401k,
          rothIraBalance: accounts.rothIra,
          brokerageBalance: accounts.brokerage,
          realEstateBalance: accounts.realEstate,
          withdrawal: isRetired ? params.annualExpenses * Math.pow(1 + inflationRate, i) : 0
      });
  }

  return projections;
};

const generateSimulationResults = (params, iterations = 10000) => {
  const years = params.lifeExpectancy - params.currentAge;
  const peakValues = [];
  const minValues = [];
  
  for (let iteration = 0; iteration < iterations; iteration++) {
    let accounts = {
      hsa: params.accounts.hsa.balance,
      retirement401k: params.accounts.retirement401k.balance,
      rothIra: params.accounts.rothIra.balance,
      brokerage: params.accounts.brokerage.balance,
      realEstate: params.accounts.realEstate.balance
    };
    
    const returns = {
      hsa: generateReturns(years, params.accounts.hsa.expectedReturn, params.accounts.hsa.stdDev),
      retirement401k: generateReturns(years, params.accounts.retirement401k.expectedReturn, params.accounts.retirement401k.stdDev),
      rothIra: generateReturns(years, params.accounts.rothIra.expectedReturn, params.accounts.rothIra.stdDev),
      brokerage: generateReturns(years, params.accounts.brokerage.expectedReturn, params.accounts.brokerage.stdDev),
      realEstate: generateReturns(years, params.accounts.realEstate.expectedReturn, params.accounts.realEstate.stdDev)
    };

    let peakBalance = -Infinity;
    let minBalance = Infinity;
    
    for (let year = 0; year < years; year++) {
      Object.keys(accounts).forEach((accountType) => {
        const account = params.accounts[accountType];
        accounts[accountType] *= (1 + returns[accountType][year]);
        if (year < params.retirementAge - params.currentAge) {
          accounts[accountType] += account.annualContribution * Math.pow(1 + params.inflationRate / 100, year);
        }
      });

      const totalBalance = Object.values(accounts).reduce((sum, balance) => sum + balance, 0);
      peakBalance = Math.max(peakBalance, totalBalance);
      minBalance = Math.min(minBalance, totalBalance);
    }
    
    peakValues.push(peakBalance);
    minValues.push(minBalance);
  }

  // Create histogram data
  const createHistogramData = (values, bins = 50) => {
    const min = Math.min(...values);
    const max = Math.max(...values);
    const binWidth = (max - min) / bins;
    const histogram = new Array(bins).fill(0);
    
    values.forEach(value => {
      const binIndex = Math.min(Math.floor((value - min) / binWidth), bins - 1);
      histogram[binIndex]++;
    });

    return histogram.map((count, index) => ({
      value: min + (index + 0.5) * binWidth,
      count: count / values.length * 100 // Convert to percentage
    }));
  };

  return {
    peakDistribution: createHistogramData(peakValues),
    minDistribution: createHistogramData(minValues),
    medianPeak: peakValues.sort((a, b) => a - b)[Math.floor(iterations / 2)],
    medianMin: minValues.sort((a, b) => a - b)[Math.floor(iterations / 2)]
  };
};

const DistributionPlot = ({ data, title, median, color }) => (
  <Card>
    <CardHeader>
      <CardTitle>{title}</CardTitle>
      <p className="text-sm text-muted-foreground">Median: {formatCurrency(median)}</p>
    </CardHeader>
    <CardContent>
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey="value"
              tickFormatter={(value) => formatCurrency(value)}
              label={{ value: "Portfolio Value", position: "bottom" }}
            />
            <YAxis
              label={{ value: "Frequency (%)", angle: -90, position: "insideLeft" }}
            />
            <Tooltip
              formatter={(value, name) => [
                `${value.toFixed(2)}%`,
                "Frequency"
              ]}
              labelFormatter={(label) => `Value: ${formatCurrency(label)}`}
            />
            <Bar dataKey="count" fill={color} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </CardContent>
  </Card>
);

const RetirementDashboard = () => {
  const initialParams = {
    currentAge: 30,
    retirementAge: 48,
    lifeExpectancy: 90,
    annualExpenses: 70000,
    inflationRate: 2,
    accounts: {
      hsa: {
        balance: 1000,
        annualContribution: 7300,
        expectedReturn: 9.2,
        stdDev: 17,
        color: '#48bb78'
      },
      retirement401k: {
        balance: 100000,
        annualContribution: 33000,
        expectedReturn: 9.2,
        stdDev: 17,
        color: '#4299e1'
      },
      rothIra: {
        balance: 100000,
        annualContribution: 6500,
        expectedReturn: 9.2,
        stdDev: 17,
        color: '#9f7aea'
      },
      brokerage: {
        balance: 100000,
        annualContribution: 1000,
        expectedReturn: 9.2,
        stdDev: 17,
        color: '#ed8936'
      },
      realEstate: {
        balance: 100000,
        annualContribution: 4000,
        expectedReturn: 4,
        stdDev: 8,
        color: '#f56565'
      }
    }
  };
  
  const accountLabels = {
    hsa: 'HSA',
    retirement401k: '401(k)',
    rothIra: 'Roth IRA',
    brokerage: 'Brokerage',
    realEstate: 'Real Estate'
  };
  const [params, setParams] = useState(initialParams);
  const [projections, setProjections] = useState(() => generateProjections(initialParams));
  const [backgroundColor, setBackgroundColor] = useState('#ffffff');
    const successRate = projections.filter((projection) => {
    const balanceWithoutRealEstate =
      projection.hsaBalance +
      projection.retirement401kBalance +
      projection.rothIraBalance +
      projection.brokerageBalance;
    return balanceWithoutRealEstate > 0;
  }).length / projections.length * 100;
  const peakBalance = Math.max(...projections.map(p => p.totalBalance));
  const totalCurrentSavings = Object.values(params.accounts).reduce((sum, account) => sum + account.balance, 0);
  const simulationResults = useMemo(() => generateSimulationResults(params), [params]);

  const updateProjections = useCallback((newParams: React.SetStateAction<{ currentAge: number; retirementAge: number; lifeExpectancy: number; annualExpenses: number; inflationRate: number; accounts: { hsa: { balance: number; annualContribution: number; expectedReturn: number; stdDev: number; color: string; }; retirement401k: { balance: number; annualContribution: number; expectedReturn: number; stdDev: number; color: string; }; rothIra: { balance: number; annualContribution: number; expectedReturn: number; stdDev: number; color: string; }; brokerage: { balance: number; annualContribution: number; expectedReturn: number; stdDev: number; color: string; }; realEstate: { balance: number; annualContribution: number; expectedReturn: number; stdDev: number; color: string; }; }; }>) => {
    setParams(newParams);
    setProjections(generateProjections(newParams));
  }, []);

  const addNewAccount = () => {
    const newAccountId = `account${Object.keys(params.accounts).length + 1}`;
    const newParams = {
      ...params,
      accounts: {
        ...params.accounts,
        [newAccountId]: {
          balance: 0,
          annualContribution: 0,
          expectedReturn: 7,
          stdDev: 15,
          color: `#${Math.floor(Math.random()*16777215).toString(16)}`
        }
      }
    };
    updateProjections(newParams);
  };

  const removeAccount = (accountType) => {
    const newAccounts = { ...params.accounts };
    delete newAccounts[accountType];
    updateProjections({ ...params, accounts: newAccounts });
  };

  return (
    <div className="w-full max-w-6xl mx-auto p-4 space-y-6" style={{ backgroundColor }}>
    <div className="w-full max-w-6xl mx-auto p-4 space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center space-x-4">
              <DollarSign className="h-8 w-8 text-blue-500" />
              <div>
                <p className="text-sm font-medium text-muted-foreground">Current Savings</p>
                <h3 className="text-2xl font-bold">{formatCurrency(totalCurrentSavings)}</h3>
              </div>
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center space-x-4">
              <Calendar className="h-8 w-8 text-green-500" />
              <div>
                <p className="text-sm font-medium text-muted-foreground">Years Until Retirement</p>
                <h3 className="text-2xl font-bold">{params.retirementAge - params.currentAge}</h3>
              </div>
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center space-x-4">
              <TrendingUp className="h-8 w-8 text-purple-500" />
              <div>
                <p className="text-sm font-medium text-muted-foreground">Peak Balance</p>
                <h3 className="text-2xl font-bold">{formatCurrency(peakBalance)}</h3>
              </div>
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center space-x-4">
              <Percent className="h-8 w-8 text-yellow-500" />
              <div>
                <p className="text-sm font-medium text-muted-foreground">Success Rate</p>
                <h3 className="text-2xl font-bold">
                  {parseFloat(successRate.toPrecision(4))}%
                </h3>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {Object.entries(params.accounts).map(([accountType, account]) => (
          <Card key={accountType}>
            <CardContent className="pt-6">
              <div className="flex items-center space-x-4">
                <DollarSign className="h-8 w-8 text-blue-500" />
                <div>
                  <p className="text-sm font-medium text-muted-foreground">{accountLabels[accountType]}</p>
                  <h3 className="text-2xl font-bold">{formatCurrency(account.balance)}</h3>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Portfolio Balance by Account Type</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={projections}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="age" />
                  <YAxis 
                    tickFormatter={(value) => {
                      if (value >= 1_000_000) {
                        const formatted = (value / 1_000_000).toFixed(1);
                        return `${formatted.replace(/\.0$/, '')} Mil`;
                      }
                      const formatted = (value / 1_000).toFixed(1);
                      return `${formatted.replace(/\.0$/, '')} K`;
                    }}
                  />
                  <Tooltip 
                    formatter={(value) => {
                      if (value >= 1_000_000) {
                        const formatted = (value / 1_000_000).toFixed(1);
                        return `${formatted.replace(/\.0$/, '')} Mil`;
                      }
                      const formatted = (value / 1_000).toFixed(1);
                      return `${formatted.replace(/\.0$/, '')} K`;
                    }} 
                  />
                  <Legend />
                  <Area type="monotone" dataKey="hsaBalance" stackId="1" name="HSA" fill="#48bb78" />
                  <Area type="monotone" dataKey="retirement401kBalance" stackId="1" name="401(k)" fill="#4299e1" />
                  <Area type="monotone" dataKey="rothIraBalance" stackId="1" name="Roth IRA" fill="#9f7aea" />
                  <Area type="monotone" dataKey="brokerageBalance" stackId="1" name="Brokerage" fill="#ed8936" />
                  <Area type="monotone" dataKey="realEstateBalance" stackId="1" name="Real Estate" fill="#f56565" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
          <Card>
          <CardHeader>
            <CardTitle>Adjust Your Parameters</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              <div className="space-y-4">
                <Label>Current Age: {params.currentAge}</Label>
                <Slider
                  defaultValue={[params.currentAge]}
                  min={18}
                  max={80}
                  step={1}
                  onValueChange={([value]) => 
                    updateProjections({ ...params, currentAge: value })}
                />
                
                <Label>Retirement Age: {params.retirementAge}</Label>
                <Slider
                  defaultValue={[params.retirementAge]}
                  min={params.currentAge + 1}
                  max={85}
                  step={1}
                  onValueChange={([value]) => 
                    updateProjections({ ...params, retirementAge: value })}
                />
                
                <Label>Life Expectancy: {params.lifeExpectancy}</Label>
                <Slider
                  defaultValue={[params.lifeExpectancy]}
                  min={params.retirementAge + 1}
                  max={100}
                  step={1}
                  onValueChange={([value]) => 
                    updateProjections({ ...params, lifeExpectancy: value })}
                />

                <Label>Annual Expenses: {formatCurrency(params.annualExpenses)}</Label>
                <Slider
                  defaultValue={[params.annualExpenses]}
                  min={20000}
                  max={200000}
                  step={5000}
                  onValueChange={([value]) => 
                    updateProjections({ ...params, annualExpenses: value })}
                />
              </div>

              {Object.entries(params.accounts).map(([accountType, account]) => (
                <div key={accountType} className="space-y-4">
                  <Label>{accountLabels[accountType]}</Label>
                  <div className="space-y-2">
                    <Label>Current Balance: {formatCurrency(account.balance)}</Label>
                    <Slider
                      defaultValue={[account.balance]}
                      min={0}
                      max={2000000}
                      step={5000}
                      onValueChange={([value]) => {
                        const newParams = {
                          ...params,
                          accounts: {
                            ...params.accounts,
                            [accountType]: {
                              ...account,
                              balance: value
                            }
                          }
                        };
                        updateProjections(newParams);
                      }}
                    />

                    <Label>Annual Contribution: {formatCurrency(account.annualContribution)}</Label>
                    <Slider
                      defaultValue={[account.annualContribution]}
                      min={0}
                      max={50000}
                      step={500}
                      onValueChange={([value]) => {
                        const newParams = {
                          ...params,
                          accounts: {
                            ...params.accounts,
                            [accountType]: {
                              ...account,
                              annualContribution: value
                            }
                          }
                        };
                        updateProjections(newParams);
                      }}
                    />

                    <Label>Expected Return: {account.expectedReturn}%</Label>
                    <Slider
                      defaultValue={[account.expectedReturn]}
                      min={0}
                      max={15}
                      step={0.1}
                      onValueChange={([value]) => {
                        const newParams = {
                          ...params,
                          accounts: {
                            ...params.accounts,
                            [accountType]: {
                              ...account,
                              expectedReturn: value
                            }
                          }
                        };
                        updateProjections(newParams);
                      }}
                    />

                    <Label>Standard Deviation: {account.stdDev}%</Label>
                    <Slider
                      defaultValue={[account.stdDev]}
                      min={0}
                      max={30}
                      step={0.1}
                      onValueChange={([value]) => {
                        const newParams = {
                          ...params,
                          accounts: {
                            ...params.accounts,
                            [accountType]: {
                              ...account,
                              stdDev: value
                            }
                          }
                        };
                        updateProjections(newParams);
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Yearly Projections</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Age</TableHead>
                  <TableHead>Year</TableHead>
                  <TableHead>HSA</TableHead>
                  <TableHead>401(k)</TableHead>
                  <TableHead>Roth IRA</TableHead>
                  <TableHead>Brokerage</TableHead>
                  <TableHead>Real Estate</TableHead>
                  <TableHead>Total Balance</TableHead>
                  <TableHead>Withdrawal</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {projections.map((row) => (
                  <TableRow key={row.age}>
                    <TableCell>{row.age}</TableCell>
                    <TableCell>{row.year}</TableCell>
                    <TableCell>{formatCurrency(row.hsaBalance)}</TableCell>
                    <TableCell>{formatCurrency(row.retirement401kBalance)}</TableCell>
                    <TableCell>{formatCurrency(row.rothIraBalance)}</TableCell>
                    <TableCell>{formatCurrency(row.brokerageBalance)}</TableCell>
                    <TableCell>{formatCurrency(row.realEstateBalance)}</TableCell>
                    <TableCell>{formatCurrency(row.totalBalance)}</TableCell>
                    <TableCell>{formatCurrency(row.withdrawal)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
      <div className="flex justify-between items-center">
        <Button onClick={addNewAccount} className="flex items-center gap-2">
          <Plus className="h-4 w-4" /> Add Account
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Core Parameters</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-6">
            <div className="space-y-2">
              <Label>Retirement Timeline</Label>
              <div className="flex items-center gap-4">
                <Input
                  type="number"
                  value={params.currentAge}
                  onChange={(e) => updateProjections({ ...params, currentAge: parseInt(e.target.value) })}
                  className="w-20"
                />
                <div className="flex-1">
                  <Slider
                    value={[params.currentAge, params.retirementAge]}
                    min={18}
                    max={85}
                    step={1}
                    onValueChange={([current, retirement]) => 
                      updateProjections({ ...params, currentAge: current, retirementAge: retirement })}
                    className="relative"
                  >
                    <div 
                      className="absolute h-full bg-blue-200" 
                      style={{
                        left: `${((params.currentAge - 18) / (85 - 18)) * 100}%`,
                        width: `${((params.retirementAge - params.currentAge) / (85 - 18)) * 100}%`
                      }}
                    />
                  </Slider>
                </div>
                <Input
                  type="number"
                  value={params.retirementAge}
                  onChange={(e) => updateProjections({ ...params, retirementAge: parseInt(e.target.value) })}
                  className="w-20"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Life Expectancy: {params.lifeExpectancy}</Label>
              <Input
                type="number"
                value={params.lifeExpectancy}
                onChange={(e) => updateProjections({ ...params, lifeExpectancy: parseInt(e.target.value) })}
                className="w-20"
              />
              <Slider
                value={[params.lifeExpectancy]}
                min={params.retirementAge + 1}
                max={100}
                step={1}
                onValueChange={([value]) => updateProjections({ ...params, lifeExpectancy: value })}
              />
            </div>

            <div className="space-y-2">
              <Label>Annual Expenses</Label>
              <Input
                type="number"
                value={params.annualExpenses}
                onChange={(e) => updateProjections({ ...params, annualExpenses: parseInt(e.target.value) })}
                className="w-32"
              />
              <Slider
                value={[params.annualExpenses]}
                min={20000}
                max={200000}
                step={5000}
                onValueChange={([value]) => updateProjections({ ...params, annualExpenses: value })}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Object.entries(params.accounts).map(([accountType, account]) => (
          <Card key={accountType} className="relative">
            <Button
              variant="ghost"
              className="absolute top-2 right-2"
              onClick={() => removeAccount(accountType)}
            >
              <X className="h-4 w-4" />
            </Button>
            <CardHeader>
              <CardTitle>{accountLabels[accountType] || `Account ${accountType}`}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label>Current Balance</Label>
                  <Input
                    type="number"
                    value={account.balance}
                    onChange={(e) => {
                      const newParams = {
                        ...params,
                        accounts: {
                          ...params.accounts,
                          [accountType]: {
                            ...account,
                            balance: parseInt(e.target.value)
                          }
                        }
                      };
                      updateProjections(newParams);
                    }}
                  />
                  <Slider
                    value={[account.balance]}
                    min={0}
                    max={500000}
                    step={1000}
                    onValueChange={([value]) => {
                      const newParams = {
                        ...params,
                        accounts: {
                          ...params.accounts,
                          [accountType]: {
                            ...account,
                            balance: value
                          }
                        }
                      };
                      updateProjections(newParams);
                    }}
                  />
                </div>

                <div className="space-y-2">
                  <Label>Annual Contribution</Label>
                  <Input
                    type="number"
                    value={account.annualContribution}
                    onChange={(e) => {
                      const newParams = {
                        ...params,
                        accounts: {
                          ...params.accounts,
                          [accountType]: {
                            ...account,
                            annualContribution: parseInt(e.target.value)
                          }
                        }
                      };
                      updateProjections(newParams);
                    }}
                  />
                  <Slider
                    value={[account.annualContribution]}
                    min={0}
                    max={50000}
                    step={500}
                    onValueChange={([value]) => {
                      const newParams = {
                        ...params,
                        accounts: {
                          ...params.accounts,
                          [accountType]: {
                            ...account,
                            annualContribution: value
                          }
                        }
                      };
                      updateProjections(newParams);
                    }}
                  />
                </div>

                <div className="space-y-2">
                  <Label>Expected Return (%)</Label>
                  <Input
                    type="number"
                    value={account.expectedReturn}
                    onChange={(e) => {
                      const newParams = {
                        ...params,
                        accounts: {
                          ...params.accounts,
                          [accountType]: {
                            ...account,
                            expectedReturn: parseFloat(e.target.value)
                          }
                        }
                      };
                      updateProjections(newParams);
                    }}
                  />
                  <Slider
                    value={[account.expectedReturn]}
                    min={0}
                    max={15}
                    step={0.1}
                    onValueChange={([value]) => {
                      const newParams = {
                        ...params,
                        accounts: {
                          ...params.accounts,
                          [accountType]: {
                            ...account,
                            expectedReturn: value
                          }
                        }
                      };
                      updateProjections(newParams);
                    }}
                  />
                </div>

                <div className="space-y-2">
                  <Label>Standard Deviation (%)</Label>
                  <Input
                    type="number"
                    value={account.stdDev}
                    onChange={(e) => {
                      const newParams = {
                        ...params,
                        accounts: {
                          ...params.accounts,
                          [accountType]: {
                            ...account,
                            stdDev: parseFloat(e.target.value)
                          }
                        }
                      };
                      updateProjections(newParams);
                    }}
                  />
                  <Slider
                    value={[account.stdDev]}
                    min={0}
                    max={30}
                    step={0.1}
                    onValueChange={([value]) => {
                      const newParams = {
                        ...params,
                        accounts: {
                          ...params.accounts,
                          [accountType]: {
                            ...account,
                            stdDev: value
                          }
                        }
                      };
                      updateProjections(newParams);
                    }}
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <DistributionPlot
            data={simulationResults.peakDistribution}
            title="Peak Portfolio Value Distribution"
            median={simulationResults.medianPeak}
            color="#4299e1"
          />
          <DistributionPlot
            data={simulationResults.minDistribution}
            title="Minimum Portfolio Value Distribution"
            median={simulationResults.medianMin}
            color="#48bb78"
          />
        </div>
      <div className="fixed bottom-4 right-4">
        <input
          type="color"
          value={backgroundColor}
          onChange={(e) => setBackgroundColor(e.target.value)}
          className="w-12 h-12 rounded-full cursor-pointer"
        />
      </div>
    </div>
  );
};

export default RetirementDashboard;


// import React, { useState, useCallback } from 'react';
// import { 
//   LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, 
//   ResponsiveContainer, AreaChart, Area, ComposedChart, Bar
// } from 'recharts';
// import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
// import { Slider } from '@/components/ui/slider';
// import { Label } from '@/components/ui/label';
// import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
// import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
// import { DollarSign, Percent, Calendar, TrendingUp } from 'lucide-react';

// const formatCurrency = (value) => {
//   return new Intl.NumberFormat('en-US', {
//     style: 'currency',
//     currency: 'USD',
//     minimumFractionDigits: 0,
//     maximumFractionDigits: 0,
//   }).format(value);
// };

// const generateNormalReturn = (mean, stdDev) => {
//   let u1 = Math.random();
//   let u2 = Math.random();
//   let z = Math.sqrt(-2.0 * Math.log(u1)) * Math.cos(2.0 * Math.PI * u2);
//   return mean + stdDev * z;
// };

// const generateReturns = (years, mean, stdDev) => {
//   let returns = [];
//   for (let i = 0; i < years; i++) {
//     returns.push(generateNormalReturn(mean / 100, stdDev / 100));
//   }
//   return returns;
// };

// const generateAverageReturns = (params, iterations = 10000) => {
//   const years = params.lifeExpectancy - params.currentAge;
//   const aggregatedReturns = {
//       hsa: Array(years).fill(0),
//       retirement401k: Array(years).fill(0),
//       rothIra: Array(years).fill(0),
//       brokerage: Array(years).fill(0),
//       realEstate: Array(years).fill(0)
//   };

//   for (let iteration = 0; iteration < iterations; iteration++) {
//       const returns = {
//           hsa: generateReturns(years, params.accounts.hsa.expectedReturn, params.accounts.hsa.stdDev),
//           retirement401k: generateReturns(years, params.accounts.retirement401k.expectedReturn, params.accounts.retirement401k.stdDev),
//           rothIra: generateReturns(years, params.accounts.rothIra.expectedReturn, params.accounts.rothIra.stdDev),
//           brokerage: generateReturns(years, params.accounts.brokerage.expectedReturn, params.accounts.brokerage.stdDev),
//           realEstate: generateReturns(years, params.accounts.realEstate.expectedReturn, params.accounts.realEstate.stdDev)
//       };

//       Object.keys(returns).forEach((accountType) => {
//           for (let year = 0; year < years; year++) {
//               aggregatedReturns[accountType][year] += returns[accountType][year];
//           }
//       });
//   }

//   // Calculate the average return for each year
//   Object.keys(aggregatedReturns).forEach((accountType) => {
//       aggregatedReturns[accountType] = aggregatedReturns[accountType].map(
//           (total) => total / iterations
//       );
//   });

//   return aggregatedReturns;
// };

// const generateProjections = (params) => {
//   const years = params.lifeExpectancy - params.currentAge;
//   const retirementYear = params.retirementAge - params.currentAge;
//   const averageReturns = generateAverageReturns(params);
//   let projections = [];
//   let accounts = {
//       hsa: params.accounts.hsa.balance,
//       retirement401k: params.accounts.retirement401k.balance,
//       rothIra: params.accounts.rothIra.balance,
//       brokerage: params.accounts.brokerage.balance,
//       realEstate: params.accounts.realEstate.balance
//   };
//   const inflationRate = params.inflationRate / 100;

//   for (let i = 0; i < years; i++) {
//       const age = params.currentAge + i;
//       const isRetired = age >= params.retirementAge;

//       Object.keys(accounts).forEach((accountType) => {
//           const account = params.accounts[accountType];
//           accounts[accountType] *= (1 + averageReturns[accountType][i]);
//           if (!isRetired) {
//               accounts[accountType] += account.annualContribution * Math.pow(1 + inflationRate, i);
//           }
//       });

//       const totalBalance = Object.values(accounts).reduce((sum, balance) => sum + balance, 0);

//       if (isRetired) {
//           const inflationAdjustedExpenses = params.annualExpenses * Math.pow(1 + inflationRate, i);
//           let remainingWithdrawal = inflationAdjustedExpenses;
//           ['hsa', 'retirement401k', 'brokerage', 'rothIra'].forEach((account) => {
//               if (remainingWithdrawal > 0) {
//                   const withdrawal = Math.min(remainingWithdrawal, accounts[account]);
//                   accounts[account] -= withdrawal;
//                   remainingWithdrawal -= withdrawal;
//               }
//           });
//       }

//       projections.push({
//           age,
//           year: new Date().getFullYear() + i,
//           totalBalance,
//           hsaBalance: accounts.hsa,
//           retirement401kBalance: accounts.retirement401k,
//           rothIraBalance: accounts.rothIra,
//           brokerageBalance: accounts.brokerage,
//           realEstateBalance: accounts.realEstate,
//           withdrawal: isRetired ? params.annualExpenses * Math.pow(1 + inflationRate, i) : 0
//       });
//   }

//   return projections;
// };

// const RetirementDashboard = () => {
//   const initialParams = {
//     currentAge: 30,
//     retirementAge: 48,
//     lifeExpectancy: 90,
//     annualExpenses: 70000,
//     inflationRate: 2,
//     accounts: {
//       hsa: {
//         balance: 1000,
//         annualContribution: 7300,
//         expectedReturn: 9.2,
//         stdDev: 17
//       },
//       retirement401k: {
//         balance: 100000,
//         annualContribution: 33000,
//         expectedReturn: 9.2,
//         stdDev: 17
//       },
//       rothIra: {
//         balance: 100000,
//         annualContribution: 6500,
//         expectedReturn: 9.2,
//         stdDev: 17
//       },
//       brokerage: {
//         balance: 100000,
//         annualContribution: 1000,
//         expectedReturn: 9.2,
//         stdDev: 17
//       },
//       realEstate: {
//         balance: 100000,
//         annualContribution: 4000,
//         expectedReturn: 4,
//         stdDev: 8
//       }
//     }
//   };

//   const [params, setParams] = useState(initialParams);
//   const [projections, setProjections] = useState(() => generateProjections(initialParams));
  
//   const updateProjections = useCallback((newParams) => {
//     setParams(newParams);
//     setProjections(generateProjections(newParams));
//   }, []);
  
//   const accountLabels = {
//     hsa: 'HSA',
//     retirement401k: '401(k)',
//     rothIra: 'Roth IRA',
//     brokerage: 'Brokerage',
//     realEstate: 'Real Estate'
//   };
  
//   const successRate = projections.filter((projection) => {
//     const balanceWithoutRealEstate =
//       projection.hsaBalance +
//       projection.retirement401kBalance +
//       projection.rothIraBalance +
//       projection.brokerageBalance;
//     return balanceWithoutRealEstate > 0;
//   }).length / projections.length * 100;
//   const peakBalance = Math.max(...projections.map(p => p.totalBalance));
//   const totalCurrentSavings = Object.values(params.accounts).reduce((sum, account) => sum + account.balance, 0);

//   return (
//     <div className="w-full max-w-6xl mx-auto p-4 space-y-6">
//       <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
//         <Card>
//           <CardContent className="pt-6">
//             <div className="flex items-center space-x-4">
//               <DollarSign className="h-8 w-8 text-blue-500" />
//               <div>
//                 <p className="text-sm font-medium text-muted-foreground">Current Savings</p>
//                 <h3 className="text-2xl font-bold">{formatCurrency(totalCurrentSavings)}</h3>
//               </div>
//             </div>
//           </CardContent>
//         </Card>
        
//         <Card>
//           <CardContent className="pt-6">
//             <div className="flex items-center space-x-4">
//               <Calendar className="h-8 w-8 text-green-500" />
//               <div>
//                 <p className="text-sm font-medium text-muted-foreground">Years Until Retirement</p>
//                 <h3 className="text-2xl font-bold">{params.retirementAge - params.currentAge}</h3>
//               </div>
//             </div>
//           </CardContent>
//         </Card>
        
//         <Card>
//           <CardContent className="pt-6">
//             <div className="flex items-center space-x-4">
//               <TrendingUp className="h-8 w-8 text-purple-500" />
//               <div>
//                 <p className="text-sm font-medium text-muted-foreground">Peak Balance</p>
//                 <h3 className="text-2xl font-bold">{formatCurrency(peakBalance)}</h3>
//               </div>
//             </div>
//           </CardContent>
//         </Card>
        
//         <Card>
//           <CardContent className="pt-6">
//             <div className="flex items-center space-x-4">
//               <Percent className="h-8 w-8 text-yellow-500" />
//               <div>
//                 <p className="text-sm font-medium text-muted-foreground">Success Rate</p>
//                 <h3 className="text-2xl font-bold">
//                   {parseFloat(successRate.toPrecision(4))}%
//                 </h3>
//               </div>
//             </div>
//           </CardContent>
//         </Card>
//       </div>
      
//       <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
//         {Object.entries(params.accounts).map(([accountType, account]) => (
//           <Card key={accountType}>
//             <CardContent className="pt-6">
//               <div className="flex items-center space-x-4">
//                 <DollarSign className="h-8 w-8 text-blue-500" />
//                 <div>
//                   <p className="text-sm font-medium text-muted-foreground">{accountLabels[accountType]}</p>
//                   <h3 className="text-2xl font-bold">{formatCurrency(account.balance)}</h3>
//                 </div>
//               </div>
//             </CardContent>
//           </Card>
//         ))}
//       </div>

//       <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
//         <Card>
//           <CardHeader>
//             <CardTitle>Portfolio Balance by Account Type</CardTitle>
//           </CardHeader>
//           <CardContent>
//             <div className="h-80">
//               <ResponsiveContainer width="100%" height="100%">
//                 <AreaChart data={projections}>
//                   <CartesianGrid strokeDasharray="3 3" />
//                   <XAxis dataKey="age" />
//                   <YAxis 
//                     tickFormatter={(value) => {
//                       if (value >= 1_000_000) {
//                         const formatted = (value / 1_000_000).toFixed(1);
//                         return `${formatted.replace(/\.0$/, '')} Mil`;
//                       }
//                       const formatted = (value / 1_000).toFixed(1);
//                       return `${formatted.replace(/\.0$/, '')} K`;
//                     }}
//                   />
//                   <Tooltip 
//                     formatter={(value) => {
//                       if (value >= 1_000_000) {
//                         const formatted = (value / 1_000_000).toFixed(1);
//                         return `${formatted.replace(/\.0$/, '')} Mil`;
//                       }
//                       const formatted = (value / 1_000).toFixed(1);
//                       return `${formatted.replace(/\.0$/, '')} K`;
//                     }} 
//                   />
//                   <Legend />
//                   <Area type="monotone" dataKey="hsaBalance" stackId="1" name="HSA" fill="#48bb78" />
//                   <Area type="monotone" dataKey="retirement401kBalance" stackId="1" name="401(k)" fill="#4299e1" />
//                   <Area type="monotone" dataKey="rothIraBalance" stackId="1" name="Roth IRA" fill="#9f7aea" />
//                   <Area type="monotone" dataKey="brokerageBalance" stackId="1" name="Brokerage" fill="#ed8936" />
//                   <Area type="monotone" dataKey="realEstateBalance" stackId="1" name="Real Estate" fill="#f56565" />
//                 </AreaChart>
//               </ResponsiveContainer>
//             </div>
//           </CardContent>
//         </Card>


//           <Card>
//           <CardHeader>
//             <CardTitle>Adjust Your Parameters</CardTitle>
//           </CardHeader>
//           <CardContent>
//             <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
//               <div className="space-y-4">
//                 <Label>Current Age: {params.currentAge}</Label>
//                 <Slider
//                   defaultValue={[params.currentAge]}
//                   min={18}
//                   max={80}
//                   step={1}
//                   onValueChange={([value]) => 
//                     updateProjections({ ...params, currentAge: value })}
//                 />
                
//                 <Label>Retirement Age: {params.retirementAge}</Label>
//                 <Slider
//                   defaultValue={[params.retirementAge]}
//                   min={params.currentAge + 1}
//                   max={85}
//                   step={1}
//                   onValueChange={([value]) => 
//                     updateProjections({ ...params, retirementAge: value })}
//                 />
                
//                 <Label>Life Expectancy: {params.lifeExpectancy}</Label>
//                 <Slider
//                   defaultValue={[params.lifeExpectancy]}
//                   min={params.retirementAge + 1}
//                   max={100}
//                   step={1}
//                   onValueChange={([value]) => 
//                     updateProjections({ ...params, lifeExpectancy: value })}
//                 />

//                 <Label>Annual Expenses: {formatCurrency(params.annualExpenses)}</Label>
//                 <Slider
//                   defaultValue={[params.annualExpenses]}
//                   min={20000}
//                   max={200000}
//                   step={5000}
//                   onValueChange={([value]) => 
//                     updateProjections({ ...params, annualExpenses: value })}
//                 />
//               </div>

//               {Object.entries(params.accounts).map(([accountType, account]) => (
//                 <div key={accountType} className="space-y-4">
//                   <Label>{accountLabels[accountType]}</Label>
//                   <div className="space-y-2">
//                     <Label>Current Balance: {formatCurrency(account.balance)}</Label>
//                     <Slider
//                       defaultValue={[account.balance]}
//                       min={0}
//                       max={2000000}
//                       step={5000}
//                       onValueChange={([value]) => {
//                         const newParams = {
//                           ...params,
//                           accounts: {
//                             ...params.accounts,
//                             [accountType]: {
//                               ...account,
//                               balance: value
//                             }
//                           }
//                         };
//                         updateProjections(newParams);
//                       }}
//                     />

//                     <Label>Annual Contribution: {formatCurrency(account.annualContribution)}</Label>
//                     <Slider
//                       defaultValue={[account.annualContribution]}
//                       min={0}
//                       max={50000}
//                       step={500}
//                       onValueChange={([value]) => {
//                         const newParams = {
//                           ...params,
//                           accounts: {
//                             ...params.accounts,
//                             [accountType]: {
//                               ...account,
//                               annualContribution: value
//                             }
//                           }
//                         };
//                         updateProjections(newParams);
//                       }}
//                     />

//                     <Label>Expected Return: {account.expectedReturn}%</Label>
//                     <Slider
//                       defaultValue={[account.expectedReturn]}
//                       min={0}
//                       max={15}
//                       step={0.1}
//                       onValueChange={([value]) => {
//                         const newParams = {
//                           ...params,
//                           accounts: {
//                             ...params.accounts,
//                             [accountType]: {
//                               ...account,
//                               expectedReturn: value
//                             }
//                           }
//                         };
//                         updateProjections(newParams);
//                       }}
//                     />

//                     <Label>Standard Deviation: {account.stdDev}%</Label>
//                     <Slider
//                       defaultValue={[account.stdDev]}
//                       min={0}
//                       max={30}
//                       step={0.1}
//                       onValueChange={([value]) => {
//                         const newParams = {
//                           ...params,
//                           accounts: {
//                             ...params.accounts,
//                             [accountType]: {
//                               ...account,
//                               stdDev: value
//                             }
//                           }
//                         };
//                         updateProjections(newParams);
//                       }}
//                     />
//                   </div>
//                 </div>
//               ))}
//             </div>
//           </CardContent>
//         </Card>
        
//       </div>

//       <Card>
//         <CardHeader>
//           <CardTitle>Yearly Projections</CardTitle>
//         </CardHeader>
//         <CardContent>
//           <div className="overflow-x-auto">
//             <Table>
//               <TableHeader>
//                 <TableRow>
//                   <TableHead>Age</TableHead>
//                   <TableHead>Year</TableHead>
//                   <TableHead>HSA</TableHead>
//                   <TableHead>401(k)</TableHead>
//                   <TableHead>Roth IRA</TableHead>
//                   <TableHead>Brokerage</TableHead>
//                   <TableHead>Real Estate</TableHead>
//                   <TableHead>Total Balance</TableHead>
//                   <TableHead>Withdrawal</TableHead>
//                 </TableRow>
//               </TableHeader>
//               <TableBody>
//                 {projections.map((row) => (
//                   <TableRow key={row.age}>
//                     <TableCell>{row.age}</TableCell>
//                     <TableCell>{row.year}</TableCell>
//                     <TableCell>{formatCurrency(row.hsaBalance)}</TableCell>
//                     <TableCell>{formatCurrency(row.retirement401kBalance)}</TableCell>
//                     <TableCell>{formatCurrency(row.rothIraBalance)}</TableCell>
//                     <TableCell>{formatCurrency(row.brokerageBalance)}</TableCell>
//                     <TableCell>{formatCurrency(row.realEstateBalance)}</TableCell>
//                     <TableCell>{formatCurrency(row.totalBalance)}</TableCell>
//                     <TableCell>{formatCurrency(row.withdrawal)}</TableCell>
//                   </TableRow>
//                 ))}
//               </TableBody>
//             </Table>
//           </div>
//         </CardContent>
//       </Card>
//     </div>
//   );
// };

// export default RetirementDashboard;
